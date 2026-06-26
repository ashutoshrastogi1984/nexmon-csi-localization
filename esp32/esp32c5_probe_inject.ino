/*
 * ESP32-C5 Probe Request Injector — Arduino IDE version
 *
 * Board: "ESP32C5 Dev Module" in Arduino IDE (esp32 core ≥ 3.x)
 * Partition: Default (no OTA needed)
 *
 * This sends 802.11 probe requests on ch44 (5220 MHz) every 100ms.
 * The frame uses management type (fc=0x40) → Nexmon stores real SA in src_mac.
 *
 * STEP 1: Flash this, open Serial Monitor at 115200 baud.
 * STEP 2: Note the printed MAC (either SRC_MAC below or actual HW MAC).
 * STEP 3: Update your tcpdump + nexmon_csi.py calls with that MAC.
 */

#include "esp_wifi.h"
#include "esp_netif.h"
#include "nvs_flash.h"

/* ── Config ──────────────────────────────────────────────────────────────── */
#define WIFI_CHANNEL     44
#define PROBE_SSID       "Asus86u_5G"
#define PROBE_INTERVAL   50   /* ms between probe requests */

/* Fixed source MAC embedded in the 802.11 SA field.
 * Nexmon reads SA from the mgmt frame → this is what --mac should match.
 * Locally administered bit set (0x02) to avoid conflicts with real devices. */
static const uint8_t SRC_MAC[6] = { 0xD0, 0xCF, 0x13, 0xE2, 0x88, 0x94 };

/* ── Frame buffer ─────────────────────────────────────────────────────────  */
static uint8_t probe_frame[64];
static uint16_t seq_num = 0;
static int frame_len = 0;

void buildProbeFrame() {
    static const uint8_t bcast[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
    memset(probe_frame, 0, sizeof(probe_frame));

    /* Frame Control: subtype=4 (probe req), type=0 (mgmt) */
    probe_frame[0] = 0x40; probe_frame[1] = 0x00;
    /* Duration */
    probe_frame[2] = 0x00; probe_frame[3] = 0x00;
    /* DA */
    memcpy(&probe_frame[4],  bcast,   6);
    /* SA — this is what nexmon captures in src_mac */
    memcpy(&probe_frame[10], SRC_MAC, 6);
    /* BSSID */
    memcpy(&probe_frame[16], bcast,   6);
    /* Seq/Frag — will be patched each TX */
    probe_frame[22] = 0x00; probe_frame[23] = 0x00;

    int off = 24;

    /* IE: SSID */
    uint8_t ssid_len = strlen(PROBE_SSID);
    probe_frame[off++] = 0x00;
    probe_frame[off++] = ssid_len;
    memcpy(&probe_frame[off], PROBE_SSID, ssid_len);
    off += ssid_len;

    /* IE: Supported Rates */
    probe_frame[off++] = 0x01; probe_frame[off++] = 0x08;
    probe_frame[off++] = 0x82; probe_frame[off++] = 0x84;
    probe_frame[off++] = 0x8B; probe_frame[off++] = 0x96;
    probe_frame[off++] = 0x0C; probe_frame[off++] = 0x12;
    probe_frame[off++] = 0x18; probe_frame[off++] = 0x24;

    /* IE: Extended Supported Rates */
    probe_frame[off++] = 0x32; probe_frame[off++] = 0x04;
    probe_frame[off++] = 0x30; probe_frame[off++] = 0x48;
    probe_frame[off++] = 0x60; probe_frame[off++] = 0x6C;

    /* IE: DS Parameter Set */
    probe_frame[off++] = 0x03; probe_frame[off++] = 0x01;
    probe_frame[off++] = WIFI_CHANNEL;

    frame_len = off;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n=== ESP32-C5 Probe Request Injector ===");

    /* NVS init */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    /* Minimal WiFi init in STA mode */
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_mode(WIFI_MODE_STA);

    wifi_config_t sta_cfg = {};
    memcpy(sta_cfg.sta.ssid, PROBE_SSID, strlen(PROBE_SSID));
    sta_cfg.sta.channel = WIFI_CHANNEL;
    esp_wifi_set_config(WIFI_IF_STA, &sta_cfg);
    esp_wifi_start();

    // Keep WiFi radio active to maintain current draw above powerbank cutoff 
    esp_wifi_set_ps(WIFI_PS_NONE);

    /* Lock to ch44 with upper secondary channel (80MHz alignment) */
    esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_ABOVE);

    /* Print HW MAC for reference */
    uint8_t hw_mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, hw_mac);
    Serial.printf("HW MAC:     %02x:%02x:%02x:%02x:%02x:%02x\n",
                  hw_mac[0], hw_mac[1], hw_mac[2], hw_mac[3], hw_mac[4], hw_mac[5]);
    Serial.printf("Frame SA:   %02x:%02x:%02x:%02x:%02x:%02x  ← use this for --mac\n",
                  SRC_MAC[0], SRC_MAC[1], SRC_MAC[2], SRC_MAC[3], SRC_MAC[4], SRC_MAC[5]);
    Serial.printf("Channel:    %d (5220 MHz)\n", WIFI_CHANNEL);
    Serial.printf("Interval:   %d ms\n\n", PROBE_INTERVAL);
    Serial.println("Capture command:");
    Serial.printf("  sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w pos1_esp32.pcap\n\n");
    Serial.println("Parser command (after capture):");
    Serial.printf("  python3 ~/parser_check/nexmon_csi.py pos1_esp32.pcap --mac %02x:%02x:%02x:%02x:%02x:%02x\n",
                  SRC_MAC[0], SRC_MAC[1], SRC_MAC[2], SRC_MAC[3], SRC_MAC[4], SRC_MAC[5]);

    buildProbeFrame();
    Serial.printf("\nProbe frame built (%d bytes). Starting injection...\n", frame_len);
}

void loop() {
    /* Patch sequence number */
    uint16_t sc = (seq_num & 0x0FFF) << 4;
    probe_frame[22] = sc & 0xFF;
    probe_frame[23] = (sc >> 8) & 0xFF;
    seq_num = (seq_num + 1) & 0x0FFF;

    esp_err_t err = esp_wifi_80211_tx(WIFI_IF_STA, probe_frame, frame_len, false);

    static uint32_t count = 0;
    count++;
    if (count % 100 == 0) {
        Serial.printf("Sent %lu probe requests (last err: %s)\n",
                      (unsigned long)count, esp_err_to_name(err));
    }

    delay(PROBE_INTERVAL);
}
