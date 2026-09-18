"""What to do about each failing security check, in English and Thai.

This is content, not logic, and it is kept out of the translation catalogues
on purpose: these entries are paragraphs carrying shell and PowerShell
commands, and .po files are built for short interface strings. A translator
working through messages.po should not be deciding how to quote a registry
path.

Every entry that can break something says so. A remediation note that gives
the command and stops there is a trap: enabling a host firewall without
allowing SSH first locks you out of the machine, and turning off SSH password
authentication cuts off this monitor, which signs in with a password. The
`warning` field is not decoration -- for several of these checks it is the
part that matters most.

Keyed by platform because the two share check names: `firewall` means ufw or
firewalld on Linux and Windows Firewall profiles on Windows, and the fixes
have nothing in common.
"""

WINDOWS = {
    'firewall': {
        'label': {
            'en': 'Windows Firewall enabled',
            'th': 'เปิด Windows Firewall',
        },
        'fix': {
            'en': 'Enable all three profiles, from an elevated PowerShell on the host.',
            'th': 'เปิดให้ครบทั้งสาม profile โดยรัน PowerShell ด้วยสิทธิ์ Administrator บนเครื่องนั้น',
        },
        'command': 'Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True',
        'warning': {
            'en': 'Check the inbound rules first. If the rules for WinRM (5985/5986) '
                  'or RDP (3389) are missing, turning the firewall on can cut off both '
                  'this monitor and your own way back into the host.',
            'th': 'ตรวจ inbound rule ก่อน ถ้ากฎสำหรับ WinRM (5985/5986) หรือ RDP (3389) หายไป '
                  'การเปิด firewall จะตัดทั้งการมอนิเตอร์และทางที่คุณใช้เข้าเครื่องนี้เอง',
        },
    },
    'av_realtime': {
        'label': {
            'en': 'Antivirus real-time protection on',
            'th': 'เปิดการป้องกันแบบเรียลไทม์ของแอนตี้ไวรัส',
        },
        'fix': {
            'en': 'If the host runs Microsoft Defender, turn real-time monitoring back on. '
                  'If no antivirus is installed at all, installing one is the fix -- there '
                  'is nothing to switch on.',
            'th': 'ถ้าเครื่องใช้ Microsoft Defender ให้เปิด real-time monitoring กลับ '
                  'แต่ถ้าเครื่องไม่มีแอนตี้ไวรัสติดตั้งอยู่เลย การติดตั้งคือวิธีแก้ ไม่ใช่การสั่งเปิด '
                  'เพราะไม่มีอะไรให้เปิด',
        },
        'command': 'Set-MpPreference -DisableRealtimeMonitoring $false',
        'warning': {
            'en': 'Windows Server 2012 R2 has no Defender and Server 2016 does not install '
                  'it by default, so on those builds the command above will not exist. '
                  'Those hosts need a real antivirus product installed.',
            'th': 'Windows Server 2012 R2 ไม่มี Defender และ Server 2016 ก็ไม่ได้ติดตั้งมาให้ '
                  'คำสั่งข้างบนจะไม่มีบนเครื่องพวกนั้น ต้องติดตั้งแอนตี้ไวรัสจริง ๆ แทน',
        },
    },
    'av_signature': {
        'label': {
            'en': 'Antivirus signatures current',
            'th': 'ฐานข้อมูลไวรัสเป็นปัจจุบัน',
        },
        'fix': {
            'en': 'Update the definitions from the host, or from the management console '
                  'of whichever antivirus product it runs.',
            'th': 'สั่งอัปเดตฐานข้อมูลจากตัวเครื่อง หรือจาก management console ของแอนตี้ไวรัสยี่ห้อนั้น',
        },
        'command': 'Update-MpSignature',
        'warning': {
            'en': 'Definitions usually fall behind because the host cannot reach the '
                  'update servers. Check the Internet column for this host before treating '
                  'it as an antivirus problem.',
            'th': 'ฐานข้อมูลมักเก่าเพราะเครื่องออกอินเทอร์เน็ตไม่ได้ ดูคอลัมน์ Internet '
                  'ของเครื่องนี้ก่อน อย่าเพิ่งสรุปว่าเป็นปัญหาที่ตัวแอนตี้ไวรัส',
        },
    },
    'patch_age': {
        'label': {
            'en': 'Operating system patched recently',
            'th': 'ระบบปฏิบัติการได้รับแพตช์ล่าสุด',
        },
        'fix': {
            'en': 'Install the outstanding updates through Windows Update, WSUS, or '
                  'sconfig option 6 on a Server Core host.',
            'th': 'ติดตั้งอัปเดตที่ค้างผ่าน Windows Update, WSUS หรือ sconfig ข้อ 6 '
                  'ถ้าเป็น Server Core',
        },
        'command': None,
        'warning': {
            'en': 'A host years behind will need several rounds of updates and several '
                  'restarts, not one. Book a maintenance window and take a snapshot or a '
                  'backup first -- this is the check most likely to need a rollback.',
            'th': 'เครื่องที่ค้างมาหลายปีต้องอัปเดตหลายรอบและรีสตาร์ทหลายครั้ง ไม่ใช่รอบเดียวจบ '
                  'จอง maintenance window และทำ snapshot หรือ backup ไว้ก่อน '
                  'ข้อนี้เป็นข้อที่มีโอกาสต้อง rollback มากที่สุด',
        },
    },
    'smb1': {
        'label': {
            'en': 'SMBv1 disabled',
            'th': 'ปิดโปรโตคอล SMBv1',
        },
        'fix': {
            'en': 'Turn the SMBv1 server protocol off, then remove the feature so it '
                  'cannot come back.',
            'th': 'ปิดโปรโตคอล SMBv1 ฝั่งเซิร์ฟเวอร์ แล้วถอน feature ออกเพื่อไม่ให้กลับมาอีก',
        },
        'command': 'Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force\n'
                   'Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol',
        'warning': {
            'en': 'Anything that still speaks only SMBv1 loses access to this host\'s file '
                  'shares the moment this takes effect: Windows XP and Server 2003, older '
                  'copiers and scanners with scan-to-folder, and older NAS boxes. Check for '
                  'those before you run it.',
            'th': 'อุปกรณ์ที่ยังพูดได้แค่ SMBv1 จะเข้าไฟล์แชร์ของเครื่องนี้ไม่ได้ทันทีที่มีผล — '
                  'Windows XP และ Server 2003, เครื่องถ่ายเอกสารและสแกนเนอร์รุ่นเก่าที่ใช้ '
                  'scan-to-folder, และ NAS รุ่นเก่า ตรวจก่อนว่ามีอุปกรณ์พวกนี้อยู่ไหม',
        },
    },
    'rdp_nla': {
        'label': {
            'en': 'RDP requires Network Level Authentication',
            'th': 'RDP บังคับใช้ Network Level Authentication',
        },
        'fix': {
            'en': 'Require NLA on the RDP listener, so a session is authenticated before '
                  'a desktop is created.',
            'th': 'ตั้งให้ RDP บังคับ NLA เพื่อให้ยืนยันตัวตนก่อน แล้วค่อยสร้าง session เดสก์ท็อป',
        },
        'command': "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\"
                   "Terminal Server\\WinStations\\RDP-Tcp' -Name UserAuthentication -Value 1",
        'warning': {
            'en': 'RDP clients older than version 6.0 (Windows XP without SP3, and some '
                  'thin clients) cannot connect once NLA is required.',
            'th': 'ไคลเอนต์ RDP ที่เก่ากว่าเวอร์ชัน 6.0 (Windows XP ที่ยังไม่ลง SP3 '
                  'และ thin client บางรุ่น) จะต่อเข้าไม่ได้หลังบังคับ NLA',
        },
    },
    'guest_account': {
        'label': {
            'en': 'Built-in Guest account disabled',
            'th': 'ปิดบัญชี Guest ที่มีมากับระบบ',
        },
        'fix': {
            'en': 'Disable the built-in Guest account.',
            'th': 'ปิดบัญชี Guest ที่ติดมากับระบบ',
        },
        'command': 'Disable-LocalUser -Name Guest',
        'warning': {
            'en': 'Rarely breaks anything, but an old share or application that relies on '
                  'guest access will stop working.',
            'th': 'ปกติไม่กระทบอะไร แต่ถ้ามีไฟล์แชร์หรือแอปเก่าที่อาศัยการเข้าถึงแบบ guest '
                  'อยู่ มันจะใช้งานไม่ได้',
        },
    },
    'pending_reboot': {
        'label': {
            'en': 'No restart pending for applied patches',
            'th': 'ไม่มีการรีสตาร์ทค้างจากแพตช์ที่ติดตั้งแล้ว',
        },
        'fix': {
            'en': 'Restart the host during a maintenance window.',
            'th': 'รีสตาร์ทเครื่องในช่วง maintenance window',
        },
        'command': 'Restart-Computer',
        'warning': {
            'en': 'Until it restarts, the patches are installed but not in effect -- the '
                  'host is still exposed to whatever they fixed.',
            'th': 'ตราบใดที่ยังไม่รีสตาร์ท แพตช์ที่ติดตั้งไว้จะยังไม่มีผล '
                  'เครื่องยังเปิดช่องโหว่ที่แพตช์นั้นแก้อยู่เหมือนเดิม',
        },
    },
}

LINUX = {
    'firewall': {
        'label': {
            'en': 'Host firewall active',
            'th': 'เปิดไฟร์วอลล์ของเครื่อง',
        },
        'fix': {
            'en': 'Allow SSH first, then enable the firewall. The order matters.',
            'th': 'อนุญาต SSH ก่อน แล้วค่อยเปิดไฟร์วอลล์ ลำดับสำคัญมาก',
        },
        'command': 'sudo ufw allow OpenSSH\nsudo ufw enable',
        'warning': {
            'en': 'Running "ufw enable" before allowing SSH locks you out of the host '
                  'immediately, and out of this monitor with it. If you are not certain '
                  'SSH is allowed, have console or out-of-band access open before you run '
                  'the second line.',
            'th': 'ถ้าสั่ง "ufw enable" ก่อนอนุญาต SSH คุณจะถูกตัดออกจากเครื่องทันที '
                  'และการมอนิเตอร์จะขาดไปด้วย ถ้าไม่มั่นใจว่า SSH ถูกอนุญาตแล้ว '
                  'ให้เปิดทาง console หรือ out-of-band ไว้ก่อนรันบรรทัดที่สอง',
        },
    },
    'ssh_root_login': {
        'label': {
            'en': 'SSH root login restricted',
            'th': 'จำกัดการล็อกอิน root ผ่าน SSH',
        },
        'fix': {
            'en': 'Set PermitRootLogin to prohibit-password (key only) or no in '
                  '/etc/ssh/sshd_config, then reload sshd.',
            'th': 'ตั้ง PermitRootLogin เป็น prohibit-password (ใช้ key เท่านั้น) หรือ no '
                  'ใน /etc/ssh/sshd_config แล้ว reload sshd',
        },
        'command': "sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "
                   '/etc/ssh/sshd_config\nsudo sshd -t && sudo systemctl reload sshd',
        'warning': {
            'en': 'Before you reload: make sure another account can sign in and reach root '
                  'through sudo, and test it in a second session while the first one is '
                  'still open. Check how this monitor signs in, too -- if it connects as '
                  'root, change its credentials first or monitoring for this host stops.',
            'th': 'ก่อน reload ต้องแน่ใจว่ามีบัญชีอื่นที่ล็อกอินได้และ sudo เป็น root ได้ '
                  'และทดสอบใน session ที่สองขณะที่ session แรกยังเปิดอยู่ '
                  'และตรวจด้วยว่า monitor ตัวนี้ล็อกอินด้วยบัญชีอะไร ถ้าใช้ root อยู่ '
                  'ต้องเปลี่ยน credential ของ monitor ก่อน ไม่งั้นการมอนิเตอร์เครื่องนี้จะหยุด',
        },
    },
    'ssh_password_auth': {
        'label': {
            'en': 'SSH password authentication disabled',
            'th': 'ปิดการล็อกอิน SSH ด้วยรหัสผ่าน',
        },
        'fix': {
            'en': 'Install a public key for every account that needs to sign in, confirm '
                  'key login works, then set PasswordAuthentication no and reload sshd.',
            'th': 'ติดตั้ง public key ให้ทุกบัญชีที่ต้องล็อกอิน ทดสอบว่าเข้าด้วย key ได้จริง '
                  'แล้วค่อยตั้ง PasswordAuthentication no และ reload sshd',
        },
        'command': 'ssh-copy-id user@host\n'
                   "sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "
                   '/etc/ssh/sshd_config\nsudo sshd -t && sudo systemctl reload sshd',
        'warning': {
            'en': 'This monitor signs in over SSH with a password. Turning password '
                  'authentication off without moving it to a key first will stop it '
                  'collecting from this host. On Ubuntu, check /etc/ssh/sshd_config.d/ as '
                  'well -- a drop-in file there overrides the main config.',
            'th': 'monitor ตัวนี้ล็อกอิน SSH ด้วยรหัสผ่าน ถ้าปิด password authentication '
                  'โดยยังไม่ย้ายไปใช้ key ก่อน มันจะเก็บข้อมูลจากเครื่องนี้ไม่ได้ '
                  'และบน Ubuntu ให้ดู /etc/ssh/sshd_config.d/ ด้วย '
                  'เพราะไฟล์ในนั้นมีผลเหนือไฟล์หลัก',
        },
    },
    'patch_updates': {
        'label': {
            'en': 'No pending security updates',
            'th': 'ไม่มีอัปเดตความปลอดภัยค้าง',
        },
        'fix': {
            'en': 'Install the pending updates.',
            'th': 'ติดตั้งอัปเดตที่ค้างอยู่',
        },
        'command': 'sudo apt update && sudo apt upgrade        # Debian / Ubuntu\n'
                   'sudo dnf upgrade --security                 # RHEL / Rocky / Alma',
        'warning': {
            'en': 'Do it in a maintenance window, and check /var/run/reboot-required '
                  'afterwards: a kernel update does nothing until the host restarts.',
            'th': 'ทำในช่วง maintenance window และตรวจ /var/run/reboot-required หลังทำเสร็จ '
                  'เพราะอัปเดต kernel จะยังไม่มีผลจนกว่าจะรีสตาร์ท',
        },
    },
    'root_equivalent_accounts': {
        'label': {
            'en': 'root is the only UID 0 account',
            'th': 'root เป็นบัญชีเดียวที่มี UID 0',
        },
        'fix': {
            'en': 'List the accounts sharing UID 0, work out what each one is for, then '
                  'give it its own UID or remove it.',
            'th': 'ดูรายชื่อบัญชีที่ใช้ UID 0 ร่วมกัน หาว่าแต่ละบัญชีมีไว้ทำอะไร '
                  'แล้วเปลี่ยนให้มี UID ของตัวเอง หรือลบทิ้ง',
        },
        'command': "awk -F: '$3==0 {print $1}' /etc/passwd",
        'warning': {
            'en': 'Never change root\'s own UID. An extra UID 0 account is a common '
                  'backdoor, so look through auth logs to find out when and by whom it was '
                  'created before you delete the evidence.',
            'th': 'ห้ามเปลี่ยน UID ของ root เอง และบัญชี UID 0 ที่เกินมาเป็นรูปแบบ backdoor '
                  'ที่พบบ่อย ควรไล่ auth log หาว่าถูกสร้างเมื่อไหร่โดยใคร '
                  'ก่อนจะลบหลักฐานทิ้ง',
        },
    },
    'empty_passwords': {
        'label': {
            'en': 'No account has an empty password',
            'th': 'ไม่มีบัญชีที่ไม่มีรหัสผ่าน',
        },
        'fix': {
            'en': 'Set a password on the account, or lock it if nobody should be signing '
                  'in as it.',
            'th': 'ตั้งรหัสผ่านให้บัญชีนั้น หรือล็อกไว้ถ้าไม่ควรมีใครล็อกอินด้วยบัญชีนี้',
        },
        'command': 'sudo passwd <user>       # set a password\n'
                   'sudo passwd -l <user>    # lock the account instead',
        'warning': {
            'en': 'An empty second field is not the same as a locked account: system '
                  'accounts normally show ! or * there and are already safe. Find out what '
                  'the account is for before changing it, in case a service signs in as it.',
            'th': 'ช่องที่สองว่างเปล่า ไม่เหมือนกับบัญชีที่ถูกล็อก — บัญชีระบบปกติจะเป็น ! หรือ * '
                  'ซึ่งปลอดภัยอยู่แล้ว ตรวจก่อนว่าบัญชีนั้นมีไว้ทำอะไร '
                  'เผื่อมีเซอร์วิสล็อกอินด้วยบัญชีนี้อยู่',
        },
    },
    'pending_reboot': {
        'label': {
            'en': 'No restart pending for applied patches',
            'th': 'ไม่มีการรีสตาร์ทค้างจากแพตช์ที่ติดตั้งแล้ว',
        },
        'fix': {
            'en': 'Check what asked for the restart, then reboot in a maintenance window.',
            'th': 'ดูว่าอะไรเป็นตัวขอให้รีสตาร์ท แล้วรีบูตในช่วง maintenance window',
        },
        'command': 'cat /var/run/reboot-required.pkgs\nsudo reboot',
        'warning': {
            'en': 'A kernel update has no effect at all until the restart happens, so the '
                  'host stays exposed to whatever it fixed.',
            'th': 'อัปเดต kernel จะไม่มีผลเลยจนกว่าจะรีสตาร์ท '
                  'เครื่องจึงยังเปิดช่องโหว่ที่อัปเดตนั้นแก้อยู่',
        },
    },
}

PLATFORMS = {'windows': WINDOWS, 'linux': LINUX}

# Where to run the commands. This belongs to the platform, not to the check --
# every Windows fix here is an elevated PowerShell cmdlet and every Linux one
# is a shell command over SSH -- so it is stored once rather than repeated on
# fifteen entries.
#
# The command block used to carry no label at all, which left the reader to
# work out for themselves that Set-SmbServerConfiguration is not something
# cmd.exe will accept.
RUN_CONTEXT = {
    'windows': {
        'en': 'PowerShell · Run as Administrator · on the affected host',
        'th': 'PowerShell · Run as Administrator · บนเครื่องที่ต้องแก้',
    },
    'linux': {
        'en': 'Shell over SSH · on the affected host',
        'th': 'Shell ผ่าน SSH · บนเครื่องที่ต้องแก้',
    },
}

SUPPORTED_LANGUAGES = ('en', 'th')

DEFAULT_LANGUAGE = 'en'


def platform_for(monitor_type):
    """Map a device's monitor_type onto the platform its advice lives under."""
    if str(monitor_type or '').lower() in ('winrm', 'wmi'):
        return 'windows'
    if str(monitor_type or '').lower() == 'ssh':
        return 'linux'
    return None


def _localise(entry, language):
    """Flatten one entry to a single language, falling back to English.

    A half-translated entry falls back field by field rather than as a whole,
    so adding a language does not mean translating everything before any of it
    can be used.
    """
    localised = {}
    for field in ('label', 'fix', 'warning'):
        value = entry.get(field) or {}
        localised[field] = value.get(language) or value.get(DEFAULT_LANGUAGE)
    # Commands are not translated: a quoted registry path or a shell flag
    # means the same thing in every language, and translating one breaks it.
    localised['command'] = entry.get('command')
    return localised


def advice_for(language=DEFAULT_LANGUAGE):
    """Every entry in one language, keyed by platform and then by check key."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    return {
        platform: {key: _localise(entry, language) for key, entry in entries.items()}
        for platform, entries in PLATFORMS.items()
    }


def run_context_for(language=DEFAULT_LANGUAGE):
    """Where each platform's commands are meant to be run, in one language."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    return {
        platform: value.get(language) or value.get(DEFAULT_LANGUAGE)
        for platform, value in RUN_CONTEXT.items()
    }
