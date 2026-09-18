"""What each security event is, and what to do when it appears.

The card can say "failed sign-in x136 from 172.41.1.249" without the reader
knowing whether that is a person fumbling a password or a machine working
through a wordlist. This is the part that closes that gap: where the event
comes from, how it happens, what it does to the host, and what to do.

Four sections on purpose, and always the same four. An operator reading the
fifth one of these should already know where to look for the bit they need.

Kept separate from security_advice.py because these answer a different
question. That module is about a configuration that is wrong and can be put
right; this one is about something that happened and may still be happening,
where the first move is usually to find out rather than to fix.
"""

DEFAULT_LANGUAGE = 'en'
SUPPORTED_LANGUAGES = ('en', 'th')

SECTIONS = ('origin', 'mechanism', 'risk', 'fix')

SECTION_LABELS = {
    'origin': {'en': 'Where it comes from', 'th': 'มาจากไหน'},
    'mechanism': {'en': 'How it happens', 'th': 'เกิดขึ้นอย่างไร'},
    'risk': {'en': 'What it does to the host', 'th': 'อันตรายต่อระบบอย่างไร'},
    'fix': {'en': 'What to do', 'th': 'แก้อย่างไร'},
}

EVENTS = {
    'failed_logon': {
        'origin': {
            'en': 'Windows writes event 4625 every time a sign-in is refused; Linux sshd '
                  'writes "Failed password". The address shown is the machine that tried, '
                  'as the host itself recorded it.',
            'th': 'ทุกครั้งที่ล็อกอินไม่ผ่าน Windows จะเขียน event 4625 เก็บไว้ ส่วน Linux เขียนเป็นบรรทัด "Failed password" ใน log ของ sshd\n\nIP ที่เห็นคือเครื่องที่พยายามเข้ามา เป็นข้อมูลที่เครื่องปลายทางบันทึกไว้เอง',
        },
        'mechanism': {
            'en': 'A few, from a machine you recognise, is usually somebody mistyping or a '
                  'saved password that has gone stale. A steady stream from one address '
                  'trying many different account names is a tool working through a list -- '
                  'no person and no service behaves that way.',
            'th': 'ถ้าเจอไม่กี่ครั้ง และมาจากเครื่องที่รู้จัก ปกติคือคนพิมพ์รหัสผิด หรือมีโปรแกรมที่จำรหัสเก่าไว้แล้วรหัสถูกเปลี่ยนไปแล้ว\n\nแต่ถ้ามาเรื่อย ๆ จาก IP เดียว แล้วไล่ชื่อบัญชีไปทีละชื่อ นั่นคือโปรแกรมที่รันอัตโนมัติ คนจริง ๆ ไม่ลองแบบนั้น และโปรแกรมที่ตั้งรหัสผิดก็จะลองชื่อเดิมซ้ำ ๆ ไม่ใช่เปลี่ยนชื่อไปเรื่อย',
        },
        'risk': {
            'en': 'Every attempt is one guess at a password. Without an account lockout '
                  'policy nothing slows it down, so given enough time a weak or reused '
                  'password is found. Network sign-ins are also used to work out which '
                  'accounts exist, because a wrong username and a wrong password are '
                  'refused in slightly different ways.',
            'th': 'แต่ละครั้งคือการเดารหัสผ่านหนึ่งครั้ง ถ้าไม่ได้ตั้ง account lockout policy ไว้ ก็ไม่มีอะไรมาหยุดมัน เดาไปเรื่อย ๆ จนกว่าจะเจอ รหัสที่เดาง่ายหรือใช้ซ้ำกับที่อื่นจึงเสี่ยงมาก\n\nอีกอย่างคือมันใช้หาได้ด้วยว่าเครื่องนี้มีบัญชีอะไรบ้าง เพราะเวลาใส่ชื่อบัญชีผิด กับใส่ชื่อถูกแต่รหัสผิด ระบบตอบกลับไม่เหมือนกันเสียทีเดียว',
        },
        'fix': {
            'en': 'Block the source address at the switch or firewall -- that stops it now. '
                  'Then check whether anything from that address ever succeeded, because '
                  'that changes this from an attempt into a break-in. Set an account lockout '
                  'policy, and make sure the host is not reachable from places it has no '
                  'business being reachable from.',
            'th': 'บล็อก IP ต้นทางที่ switch หรือ firewall ก่อน อันนี้หยุดได้ทันที\n\nจากนั้นเช็กว่ามีครั้งไหนจาก IP นั้นล็อกอินสำเร็จบ้างไหม ถ้ามี เรื่องเปลี่ยนจาก "มีคนพยายามเข้า" เป็น "มีคนเข้าไปแล้ว" ต้องรีบเปลี่ยนรหัสผ่าน\n\nแล้วตั้ง account lockout policy ไว้ และดูด้วยว่าเครื่องนี้ควรให้ใครเข้าถึงได้บ้าง ถ้าไม่จำเป็นต้องเปิดให้ทั้งวง ก็ปิดเสีย',
        },
    },
    'login_success': {
        'origin': {
            'en': 'The host recorded a sign-in that was accepted, with the account and the '
                  'address it came from.',
            'th': 'เครื่องบันทึกไว้ว่ามีการล็อกอินที่ผ่าน พร้อมบอกว่าใช้บัญชีอะไรและมาจาก IP ไหน',
        },
        'mechanism': {
            'en': 'Somebody or something authenticated correctly. On its own this is the '
                  'most ordinary event a server produces.',
            'th': 'มีคนหรือโปรแกรมใส่รหัสถูก ตัวมันเองเป็นเรื่องธรรมดาที่สุดที่เซิร์ฟเวอร์บันทึก',
        },
        'risk': {
            'en': 'It matters because of what it sits next to. A success from an address '
                  'that has also been failing means a password was finally guessed. A '
                  'success outside working hours, or for an account nobody signs in with, '
                  'is worth asking about even when nothing failed.',
            'th': 'ความสำคัญอยู่ที่ว่ามันโผล่มาคู่กับอะไร\n\nถ้าสำเร็จจาก IP เดียวกับที่ล็อกอินไม่ผ่านมาเป็นร้อยครั้ง แปลว่ารหัสถูกเดาได้แล้ว\n\nถ้าสำเร็จตอนตีสาม หรือเป็นบัญชีที่ปกติไม่มีใครใช้ล็อกอิน ก็ควรถามว่าใครเข้า ถึงแม้จะไม่มีอะไรล้มเหลวเลยก็ตาม',
        },
        'fix': {
            'en': 'Confirm it was expected. If it follows failures from the same address, '
                  'treat the host as accessed: change that account\'s password everywhere it '
                  'is used, and look for anything left behind.',
            'th': 'เช็กก่อนว่าเป็นคนของเราเข้าเองหรือเปล่า\n\nถ้ามันตามหลังการล็อกอินไม่ผ่านจาก IP เดียวกัน ให้ถือว่าเครื่องโดนเข้าไปแล้ว เปลี่ยนรหัสของบัญชีนั้นทุกที่ที่ใช้อยู่ ไม่ใช่แค่เครื่องนี้ แล้วไล่ดูว่ามีอะไรถูกทิ้งไว้บ้าง',
        },
    },
    'account_lockout': {
        'origin': {
            'en': 'Windows event 4740: an account crossed the lockout threshold and was '
                  'locked.',
            'th': 'Windows event 4740 คือบัญชีถูกล็อกเพราะใส่รหัสผิดเกินจำนวนที่ตั้งไว้',
        },
        'mechanism': {
            'en': 'Too many failures for one account inside the policy window. One account '
                  'locking again and again is usually a saved password somewhere that has '
                  'gone stale; many different accounts locking is an attack running into '
                  'the policy.',
            'th': 'ใส่รหัสผิดหลายครั้งเกินไปในช่วงเวลาที่กำหนด\n\nถ้าเป็นบัญชีเดิมโดนล็อกซ้ำ ๆ ส่วนใหญ่คือมีโปรแกรมหรือ service ที่ไหนสักแห่งจำรหัสเก่าไว้ แล้วพยายามเข้าด้วยรหัสนั้นเรื่อย ๆ\n\nถ้าโดนล็อกหลายบัญชีพร้อมกัน คือมีคนพยายามเดารหัสแล้วชน policy พอดี',
        },
        'risk': {
            'en': 'Two opposite readings. As an attack it means the policy is working. As a '
                  'stale credential it is an availability problem: the account is locked out '
                  'of its own job, and whatever uses it has stopped.',
            'th': 'อ่านได้สองแบบตรงข้ามกัน\n\nถ้าเป็นการโจมตี แปลว่า policy ทำงาน ซึ่งเป็นข่าวดี\n\nแต่ถ้าเป็นรหัสค้าง คือปัญหาเรื่องระบบใช้งานไม่ได้ บัญชีถูกล็อกออกจากงานตัวเอง และอะไรก็ตามที่ใช้บัญชีนั้นอยู่จะหยุดทำงานไปด้วย',
        },
        'fix': {
            'en': 'Find where the failures came from before unlocking, or it locks again in '
                  'minutes. If it is a service or a scheduled task holding an old password, '
                  'update it there. If it is an outside address, block it first.',
            'th': 'อย่าเพิ่งปลดล็อก หาให้เจอก่อนว่ารหัสผิดมาจากไหน ไม่งั้นอีกไม่กี่นาทีก็โดนล็อกอีก\n\nถ้าเป็น service หรือ scheduled task ที่ถือรหัสเก่าอยู่ ให้ไปแก้รหัสตรงนั้น\n\nถ้ามาจาก IP แปลก ๆ บล็อกก่อนแล้วค่อยปลดล็อก',
        },
    },
    'user_created': {
        'origin': {
            'en': 'Windows event 4720: a local account was created on this host.',
            'th': 'Windows event 4720 คือมีบัญชีใหม่ถูกสร้างขึ้นในเครื่องนี้',
        },
        'mechanism': {
            'en': 'Somebody with administrator rights made it, or a process running with '
                  'those rights did. Application installers occasionally create a service '
                  'account this way.',
            'th': 'คนที่มีสิทธิ์ Administrator สร้าง หรือโปรแกรมที่รันด้วยสิทธิ์นั้นสร้าง\n\nตัวติดตั้งโปรแกรมบางตัวก็สร้างบัญชี service ไว้ใช้งานเหมือนกัน',
        },
        'risk': {
            'en': 'This is the usual way back in after a break-in. An intruder who gains '
                  'administrator rights makes an account of their own, so that changing the '
                  'password they guessed does not shut them out.',
            'th': 'นี่คือวิธีที่คนบุกรุกใช้ทำทางกลับเข้ามา\n\nพอเขาได้สิทธิ์ Administrator แล้ว เขาจะสร้างบัญชีของตัวเองไว้ ทีนี้ต่อให้เราเปลี่ยนรหัสบัญชีที่เขาเดาได้ เขาก็ยังเข้ามาได้อยู่ดี',
        },
        'fix': {
            'en': 'Check it against planned work first. If nobody claims it, disable the '
                  'account rather than deleting it -- deleting destroys what you would want '
                  'to look at. Then check which groups it was put in, and treat the host as '
                  'compromised until you know how the account came to exist.',
            'th': 'เช็กก่อนว่ามีใครแจ้งว่าจะสร้างไหม ถ้าไม่มีใครรับ ให้ปิดการใช้งานบัญชีนั้นไว้ อย่าเพิ่งลบ\n\nที่ไม่ให้ลบเพราะพอลบแล้วหลักฐานหายหมด ทั้งที่เป็นสิ่งที่ต้องใช้ตรวจสอบ\n\nแล้วดูว่ามันถูกใส่ไว้ในกลุ่มไหนบ้าง และให้ถือว่าเครื่องนี้โดนบุกรุกไว้ก่อน จนกว่าจะรู้ว่าบัญชีนี้เกิดขึ้นมาได้ยังไง',
        },
    },
    'user_deleted': {
        'origin': {
            'en': 'Windows event 4726: a local account was removed from this host.',
            'th': 'Windows event 4726 คือมีบัญชีถูกลบออกจากเครื่องนี้',
        },
        'mechanism': {
            'en': 'Somebody with administrator rights removed it. Ordinary cleanup does this '
                  'too, which is why it matters whether the work was planned.',
            'th': 'คนที่มีสิทธิ์ Administrator ลบ งานเก็บกวาดระบบตามปกติก็ทำแบบนี้ เลยต้องดูว่าเป็นงานที่มีคนแจ้งไว้หรือเปล่า',
        },
        'risk': {
            'en': 'Two uses. Covering tracks -- removing an account that was created to get '
                  'back in, once it is no longer needed. Or denial -- removing an account '
                  'somebody else relies on.',
            'th': 'ใช้ได้สองแบบ\n\nแบบแรกคือลบร่องรอย ลบบัญชีที่สร้างไว้เพื่อกลับเข้ามา พอใช้เสร็จแล้วก็ลบทิ้ง\n\nแบบที่สองคือตัดการเข้าถึงของคนอื่น ลบบัญชีที่คนอื่นต้องใช้',
        },
        'fix': {
            'en': 'Match it to a change request. If there is none, treat it alongside any '
                  'account creation in the same period: both halves of the same move.',
            'th': 'เทียบกับใบขอเปลี่ยนแปลงก่อน ถ้าไม่มี ให้ดูคู่กับการสร้างบัญชีในช่วงเวลาใกล้ ๆ กัน เพราะสองอย่างนี้มักเป็นการกระทำเดียวกัน แค่คนละตอน',
        },
    },
    'service_installed': {
        'origin': {
            'en': 'Windows event 7045 in the System log: a new service was registered.',
            'th': 'Windows event 7045 ใน System log คือมี service ตัวใหม่ถูกลงทะเบียนเข้าระบบ',
        },
        'mechanism': {
            'en': 'Software installers do this legitimately. So do remote execution tools: '
                  'PsExec and the tools built on it work by creating a service on the target '
                  'and starting it.',
            'th': 'ตัวติดตั้งโปรแกรมทำแบบนี้ตามปกติ\n\nแต่เครื่องมือสั่งงานระยะไกลก็ทำเหมือนกัน อย่าง PsExec และเครื่องมือที่สร้างต่อจากมัน ทำงานด้วยการสร้าง service บนเครื่องปลายทางแล้วสั่งให้รัน',
        },
        'risk': {
            'en': 'A service runs as SYSTEM and starts itself at boot. That is full rights '
                  'and a way back after a restart, in one step -- which is why it is where '
                  'remote code execution usually ends up.',
            'th': 'service รันด้วยสิทธิ์ SYSTEM และสตาร์ทเองทุกครั้งที่เปิดเครื่อง\n\nแปลว่าได้ทั้งสิทธิ์สูงสุดและทางกลับเข้ามาหลังรีสตาร์ท ในขั้นตอนเดียว นี่เลยเป็นปลายทางที่การสั่งรันโค้ดระยะไกลมักไปจบลง',
        },
        'fix': {
            'en': 'Read the service name and its image path. If it does not belong to '
                  'software you installed, do not just delete it: note the path, take a copy '
                  'of the binary if you can, and treat the host as compromised. A random or '
                  'meaningless service name is a strong sign on its own.',
            'th': 'ดูชื่อ service กับ path ของไฟล์ที่มันรัน\n\nถ้าไม่ใช่ของโปรแกรมที่เราติดตั้งเอง อย่าเพิ่งลบ ให้จด path ไว้ ก๊อปไฟล์เก็บถ้าทำได้ แล้วถือว่าเครื่องโดนบุกรุก\n\nชื่อ service ที่เป็นตัวอักษรสุ่ม ๆ หรืออ่านไม่ได้ความ เป็นสัญญาณที่ชัดมากในตัวมันเอง',
        },
    },
    'log_cleared': {
        'origin': {
            'en': 'Windows event 1102: the Security log itself was cleared. The event is '
                  'written as the first entry of the now-empty log.',
            'th': 'Windows event 1102 คือมีคนล้าง Security log ทิ้ง\n\nตัว event นี้จะถูกเขียนเป็นรายการแรกของ log ที่เพิ่งว่างเปล่า',
        },
        'mechanism': {
            'en': 'It takes administrator rights, and it is a deliberate action. Nothing does '
                  'it by accident and no maintenance routine needs to.',
            'th': 'ต้องใช้สิทธิ์ Administrator และต้องตั้งใจทำ\n\nไม่มีอะไรทำโดยบังเอิญ และไม่มีงานดูแลระบบปกติที่จำเป็นต้องล้าง log',
        },
        'risk': {
            'en': 'It destroys the record of everything that happened before it. On its own '
                  'that is the finding: the usual reason to clear a log is that there was '
                  'something in it.',
            'th': 'มันลบบันทึกของทุกอย่างที่เกิดขึ้นก่อนหน้านั้นทิ้งหมด\n\nแค่นี้ก็เป็นเรื่องแล้ว เพราะเหตุผลปกติที่คนล้าง log คือในนั้นมีอะไรที่ไม่อยากให้เห็น',
        },
        'fix': {
            'en': 'Treat it as an incident from the moment you see it. The host\'s own copy '
                  'is gone, but what this monitor collected before that point is not -- the '
                  'events on this page are the surviving record, and they are worth reading '
                  'for the hours leading up to it.',
            'th': 'ให้ถือเป็นเหตุการณ์ความปลอดภัยทันทีที่เห็น\n\nของบนเครื่องหายไปแล้ว แต่สิ่งที่ monitor เก็บไว้ก่อนหน้านั้นยังอยู่ เหตุการณ์ในหน้านี้คือบันทึกที่รอดมา ให้ไล่อ่านย้อนช่วงหลายชั่วโมงก่อนที่ log จะถูกล้าง',
        },
    },
    'sudo_failed': {
        'origin': {
            'en': 'Linux pam writes an authentication failure when a sudo password is wrong, '
                  'or when the account is not allowed to use sudo at all.',
            'th': 'pam บน Linux บันทึกไว้เมื่อใส่รหัส sudo ผิด หรือเมื่อบัญชีนั้นไม่มีสิทธิ์ใช้ sudo ตั้งแต่แรก',
        },
        'mechanism': {
            'en': 'Usually somebody mistyping their own password at a prompt. Less often, an '
                  'account trying to use sudo that was never given it.',
            'th': 'ส่วนใหญ่คือคนพิมพ์รหัสตัวเองผิดตอนระบบถาม\n\nที่เจอน้อยกว่าคือบัญชีที่พยายามใช้ sudo ทั้งที่ไม่เคยได้รับสิทธิ์',
        },
        'risk': {
            'en': 'In ones and twos, none. A pattern from an account that should not be '
                  'escalating at all is different: that is somebody finding out what they '
                  'can reach with access they already have.',
            'th': 'ถ้าเจอครั้งสองครั้ง ไม่มีอะไร\n\nแต่ถ้าเป็นบัญชีที่ไม่ควรยกระดับสิทธิ์อยู่แล้ว แล้วลองซ้ำ ๆ เป็นคนละเรื่อง แปลว่ามีคนกำลังลองดูว่าสิทธิ์ที่ตัวเองมีอยู่ไปได้ไกลแค่ไหน',
        },
        'fix': {
            'en': 'Check whether that account is meant to have sudo. If it is not, the '
                  'question is no longer the password -- it is how the account came to be '
                  'signed in and what else it has been doing.',
            'th': 'เช็กว่าบัญชีนั้นควรมีสิทธิ์ sudo หรือเปล่า\n\nถ้าไม่ควรมี คำถามไม่ใช่เรื่องรหัสผ่านแล้ว แต่เป็นว่าบัญชีนี้เข้ามาล็อกอินได้ยังไง และทำอะไรไปแล้วบ้าง',
        },
    },
}


def _pick(value, language):
    value = value or {}
    return value.get(language) or value.get(DEFAULT_LANGUAGE)


def guide_for(language=DEFAULT_LANGUAGE):
    """Every entry in one language, keyed by event key."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    return {
        'sections': [
            {'key': key, 'label': _pick(SECTION_LABELS[key], language)}
            for key in SECTIONS
        ],
        'events': {
            key: {section: _pick(entry.get(section), language) for section in SECTIONS}
            for key, entry in EVENTS.items()
        },
    }
