"""Room entry configuration generators for document/scope templates."""


def generate_8000_9000_entries(rooms, configs):
    """
    Generate 8000-9000s Readings List entries
    ALWAYS USES 100s CONFIG FOR LOS VALUES
    """
    entries = []

    def _los(room_name):
        cfg = configs.get(room_name, {})
        v = cfg.get(100, cfg.get('100', '.'))
        return "…........." if v in ('.', '', None) else v

    # ── Day 0: Stabilization ─────────────────────────────────────────
    entries.append("8000 ….. ======= MC READINGS STABILIZATION ===============")
    for idx, room_name in enumerate(rooms):
        entries.append(f"{8001 + idx}.0 . {room_name} … MC READINGS STABILIZATION  {_los(room_name)}")

    # ── Day 1-4 sections ─────────────────────────────────────────────
    section_labels = {
        8100: "8100.0 . ...  DAY1    MC READINGS ..  =========  ===============  =====",
        8200: "8200.0 . ...  DAY2    MC READINGS ..  ===============  ======",
        8300: "8300.0 . ….. DAY 3 …..  =====================  ======",
        8400: "8400.0 . ….. DAY 4 …..  ===============   =======",
    }
    descs = {
        8100: "   ...  DAY1    MC READINGS .. ",
        8200: "  ...  DAY2    MC READINGS ..",
        8300: "  ...  DAY3    MC READINGS ..",
        8400: "  ...  DAY4    MC READINGS",
    }

    for work_type in [8100, 8200, 8300, 8400]:
        entries.append(section_labels[work_type])
        day_num = str(work_type)[3]
        for idx, room_name in enumerate(rooms):
            entries.append(
                f"{work_type + idx + 1}.{day_num} . {room_name} {descs[work_type]}  {_los(room_name)}"
            )

    # 7000s section label - ORIGINAL FORMAT
    entries.append("9000 RH &T & GPP  DRY CHAMBERS [DC] . READINGS ==================")

    # 7000s section (static entries - dry chambers) - ORIGINAL FORMAT
    static_7000s_entries = [
        "9100.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 1 ….. ",
        "9100.0 …. EXTERIOR & UNAFFECTED AREA  ….. DAY 1 ….. ",
        "9101.0 …. DRY CHAMBER # 1 ….. DAY 1 …..  RH &T & GPP ",
        "9102.0 …. DRY CHAMBER # 2 ….. DAY 1 …..  RH &T & GPP ",
        "9103.0 …. DRY CHAMBER # 3 ….. DAY 1 …..  RH &T & GPP ",
        "9104.0 …. DRY CHAMBER # 4 ….. DAY 1 …..  RH &T & GPP ",
        "9200.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 2 ….. ",
        "9200.2 …. EXTERIOR & UNAFFECTED AREA ….. DAY 2 ….. ",
        "9201.2 …. DRY CHAMBER # 1 ….. DAY 2 …..  RH &T & GPP ",
        "9202.2 …. DRY CHAMBER # 2 ….. DAY 2 …..  RH &T & GPP ",
        "9203.2 …. DRY CHAMBER # 3 ….. DAY 2 …..  RH &T & GPP ",
        "9204.2 …. DRY CHAMBER # 4 ….. DAY 2 …..  RH &T & GPP ",
        "9205.2 …. DRY CHAMBER # 5 ….. DAY 2 …..  RH &T & GPP ",
        "9300.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 3 ….. ",
        "9300.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 3 ….. ",
        "9301.0 …. DRY CHAMBER # 1 ….. DAY 3 …..  RH &T & GPP ",
        "9302.0 …. DRY CHAMBER # 2 ….. DAY 3 …..  RH &T & GPP ",
        "9303.0 …. DRY CHAMBER # 3 ….. DAY 3 …..  RH &T & GPP ",
        "9304.0 …. DRY CHAMBER # 4 ….. DAY 3 …..  RH &T & GPP ",
        "9400.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 4 ….. ",
        "9400.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 4 ….. ",
        "9401.0 …. DRY CHAMBER # 1 ….. DAY 4 …..  RH &T & GPP ",
        "9402.0 …. DRY CHAMBER # 2 ….. DAY 4 …..  RH &T & GPP ",
        "9403.0 …. DRY CHAMBER # 3 ….. DAY 4 …..  RH &T & GPP ",
        "9404.0 …. DRY CHAMBER # 4 ….. DAY 4 …..  RH &T & GPP "
    ]

    entries.extend(static_7000s_entries)
    return entries


def generate_8000s_entries(rooms, configs):
    """
    Generate 8000s MC Day Readings entries only (stabilization + day 1-4).
    ALWAYS USES 100s CONFIG FOR LOS VALUES.
    """
    entries = []

    def _los(room_name):
        cfg = configs.get(room_name, {})
        v = cfg.get(100, cfg.get('100', '.'))
        return "…........." if v in ('.', '', None) else v

    entries.append("8000 ….. ======= MC READINGS STABILIZATION ===============")
    for idx, room_name in enumerate(rooms):
        entries.append(f"{8001 + idx}.0 . {room_name} … MC READINGS STABILIZATION  {_los(room_name)}")

    section_labels = {
        8100: "8100.0 . ...  DAY1    MC READINGS ..  =========  ===============  =====",
        8200: "8200.0 . ...  DAY2    MC READINGS ..  ===============  ======",
        8300: "8300.0 . ….. DAY 3 …..  =====================  ======",
        8400: "8400.0 . ….. DAY 4 …..  ===============   =======",
    }
    descs = {
        8100: "   ...  DAY1    MC READINGS .. ",
        8200: "  ...  DAY2    MC READINGS ..",
        8300: "  ...  DAY3    MC READINGS ..",
        8400: "  ...  DAY4    MC READINGS",
    }
    for work_type in [8100, 8200, 8300, 8400]:
        entries.append(section_labels[work_type])
        day_num = str(work_type)[3]
        for idx, room_name in enumerate(rooms):
            entries.append(
                f"{work_type + idx + 1}.{day_num} . {room_name} {descs[work_type]}  {_los(room_name)}"
            )
    return entries


def generate_10000s_entries():
    """
    Generate Siding room list entries (static), numbered 10–20.
    """
    return [
        "10 ….. ======= SIDING =======================================",
        "11.0 . JOBSITE Verification …. SIDING",
        "12.0 . Source of LOSS/DAMAGES …. SIDING",
        "13.0 . DOOR & WINDOWS TRIM …. SIDING",
        "14.0 . SOFFIT & FASCIA …. SIDING",
        "15.0 . SDG ACCESSORIES …. SIDING",
        "16.0 . JOBSITE CONDITIONS …. SIDING",
        "17.0 . DOWN SPOUTS & GUTTERS …. SIDING",
        "18.0 . ELECTRICAL ACCESSORIES …. SIDING",
        "19.0 . DEMO & DUMPSTER …. SIDING",
        "20.0 . CLN & FINAL …. SIDING",
    ]


def generate_9000s_entries():
    """
    Generate 9000s Dry Chamber Readings entries only (static entries).
    """
    return [
        "9000 RH &T & GPP  DRY CHAMBERS [DC] . READINGS ==================",
        "9100.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 1 ….. ",
        "9100.0 …. EXTERIOR & UNAFFECTED AREA  ….. DAY 1 ….. ",
        "9101.0 …. DRY CHAMBER # 1 ….. DAY 1 …..  RH &T & GPP ",
        "9102.0 …. DRY CHAMBER # 2 ….. DAY 1 …..  RH &T & GPP ",
        "9103.0 …. DRY CHAMBER # 3 ….. DAY 1 …..  RH &T & GPP ",
        "9104.0 …. DRY CHAMBER # 4 ….. DAY 1 …..  RH &T & GPP ",
        "9200.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 2 ….. ",
        "9200.2 …. EXTERIOR & UNAFFECTED AREA ….. DAY 2 ….. ",
        "9201.2 …. DRY CHAMBER # 1 ….. DAY 2 …..  RH &T & GPP ",
        "9202.2 …. DRY CHAMBER # 2 ….. DAY 2 …..  RH &T & GPP ",
        "9203.2 …. DRY CHAMBER # 3 ….. DAY 2 …..  RH &T & GPP ",
        "9204.2 …. DRY CHAMBER # 4 ….. DAY 2 …..  RH &T & GPP ",
        "9205.2 …. DRY CHAMBER # 5 ….. DAY 2 …..  RH &T & GPP ",
        "9300.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 3 ….. ",
        "9300.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 3 ….. ",
        "9301.0 …. DRY CHAMBER # 1 ….. DAY 3 …..  RH &T & GPP ",
        "9302.0 …. DRY CHAMBER # 2 ….. DAY 3 …..  RH &T & GPP ",
        "9303.0 …. DRY CHAMBER # 3 ….. DAY 3 …..  RH &T & GPP ",
        "9304.0 …. DRY CHAMBER # 4 ….. DAY 3 …..  RH &T & GPP ",
        "9400.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 4 ….. ",
        "9400.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 4 ….. ",
        "9401.0 …. DRY CHAMBER # 1 ….. DAY 4 …..  RH &T & GPP ",
        "9402.0 …. DRY CHAMBER # 2 ….. DAY 4 …..  RH &T & GPP ",
        "9403.0 …. DRY CHAMBER # 3 ….. DAY 4 …..  RH &T & GPP ",
        "9404.0 …. DRY CHAMBER # 4 ….. DAY 4 …..  RH &T & GPP ",
    ]


def generate_70000_entries(rooms, configs):
    """
    Generate 70000s Stabilization Readings entries
    ALWAYS USES 100s CONFIG FOR LOS VALUES
    """
    entries = []

    # Add section label
    entries.append("70000 ….. ======= DAY # 0  …..  MC READINGS STABILIZATION ===============")

    for idx, room_name in enumerate(rooms):
        room_number = 70101 + idx

        # ALWAYS USE 100s CONFIG FOR LOS VALUES
        room_config = configs.get(room_name, {})
        config_value = None

        if 100 in room_config:
            config_value = room_config[100]
        elif '100' in room_config:
            config_value = room_config['100']
        else:
            config_value = '.'

        display_value = "….........." if config_value == "." else config_value

        # ORIGINAL FORMAT: {number} …. {room_name} DAY 0 MOISTURE READINGS {los_value}
        entry = f"{room_number} …. {room_name} … DAY # 0  … MC READINGS STABILIZATION … {display_value}"
        entries.append(entry)

    return entries


def generate_job_types_entries():
    """
    Generate static job types template entries (0.0000-9999.0)
    This template has HIGHEST PRIORITY and doesn't use user room data
    Format uses decimal numbers with simple space-separated descriptions for Encircle compatibility
    """
    entries = [
        "0.0001 ….. JOBSITE VERIFICATION",
        "0.0002 . MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE",
        "0.0003 . MECHANICALS = ELECTRICAL HAZARDS",
        "0.0004 . EXT DAMAGE IF APPLICABLE ROOF TARPS",
        "1997 . LEAD & HMR TESTING LAB RESULTS",
        "1998 . KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES",
        "1999 . BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE",
        "3222 . CPS DAY2 WIP OVERVIEW WIP BOXES PACKOUT PICS",
        "3322 . CPS3 DAY3 STORAGE OVERVIEW STORAGE MOVE OUT PICS",
        "3444 . CPS4 DAY4 PACKBACK OVERVIEW PACK-BACK / RESET PICS",
        "4111.1 . REPLACEMENT 1 CON OVERVIEW DAY PICS",
        "4222.2 . REPLACEMENT 2 CON WIP",
        "4333.3 . REPLACEMENT 3 CON STORAGE",
        "4444.4 . REPLACEMENT 4 CON DISPOSAL",
        "9998.0 . REBUILD OVERVIEW WORK IN PROGRESS.......WIP",
        "9999.0 . REBUILD INTERIOR COMPLETED WORK",
    ]
    return entries
