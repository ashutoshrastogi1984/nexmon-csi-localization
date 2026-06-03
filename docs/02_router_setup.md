# Step 2 — Router Setup (Merlin Firmware + SSH)

## Flash Merlin Firmware

1. Download: https://sourceforge.net/projects/asuswrt-merlin/files/RT-AC86U/Release/
   - Get latest `RT-AC86U_386.14_2.zip`
2. Router web UI → **Administration → Firmware Upgrade** → upload `.trx` file
3. Wait for reboot (~2 min). Do NOT power off during flash.

## Enable JFFS and SSH

After reboot, in web UI:

1. **Administration → System**:
   - Enable SSH Daemon → **LAN only**, port **22**
   - Enable JFFS custom scripts → **Yes**
   - Click **Apply**

2. Verify SSH works:
```bash
ssh admin@192.168.1.1
# Enter your router admin password
```

3. Verify JFFS:
```bash
ls /jffs/
# Should show: addons  configs  scripts  etc.
```

## Set Operation Mode

During initial setup wizard, select **Wireless Router** mode.
Internet connection is optional — only LAN connectivity is needed.

## Note Router IP

Default is `192.168.1.1`. Confirm with:
```bash
ip route | grep default
# e.g.: default via 192.168.1.1 dev eno1
```
