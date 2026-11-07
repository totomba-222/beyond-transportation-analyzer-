"""Static configuration: editable mappings, state names, settings defaults.

The driver->state map and Oregon school list are the ones from the original app
(preserved verbatim). They are only a *fallback*: evidence from uploaded state
reports always overrides them (see classification.py).
"""

STATE_NAMES = {
    "NM": "New Mexico (ABQ)", "IL": "Illinois", "N.CA": "North California",
    "S.CA": "South California", "AK": "Alaska", "OR": "Oregon",
    "Unassigned": "Unassigned",
}

# Arizona is an *operational reporting assignment* to S.CA, not a legal state change.
OPERATIONAL_NOTES = {"S.CA": "Includes Arizona (operational assignment)"}

DEFAULT_SETTINGS = {
    "alaska_agreed_rate": 45.00,   # configurable in the UI
    "revenue_tolerance": 0.005,    # dollars
    "payment_tolerance": 0.005,
    "mileage_tolerance": 0.51,     # miles (First rounds total miles to whole numbers)
    "low_margin_pct": 10.0,        # flag margins below this
    "fuzzy_name_cutoff": 0.92,     # secondary matching only, always flagged
}

OR_SCHOOLS = [
    "amity hs", "arata creek", "buel es", "burlingame creek", "canyon creek",
    "dexter mccarty", "edwards day", "gladstone", "gordon russell", "hall es",
    "happy valley", "heron creek", "highland es", "hollydale", "jennings lodge",
    "john wetten", "kraxberger", "kathryn jones harrison", "knott creek",
    "lifeworks", "marylhurst", "mcminnville", "meridian creek", "molalla river",
    "mulino es", "north salem", "oregon school for the deaf", "padtc",
    "patton ms", "phillips acdy", "philomath", "powell valley", "salem heights",
    "sequoia falls", "serendipity sch", "north albany", "south albany",
    "stayton ms", "structured skills", "trillium north point", "tualatin es",
    "twality", "wheatley sch", "mark twain es",
]

# Region keywords: matched as WHOLE WORDS / WHOLE PHRASES on the normalised trip
# name (never raw substrings). Used only after driver evidence fails.
# "monterey park" is listed under S.CA so it can never be read as Monterey / N.CA.
REGION_KEYWORDS = {
    "N.CA": [
        "el cerrito", "korematsu", "richmond", "dejean", "grant es", "coronado es",
        "bayhill", "san pablo", "montalvin", "dover es", "el sobrante",
        "catalyst academy", "berkeley", "san leandro", "benicia", "sierra of solano",
        "solano county", "balboa", "sacramento", "monterey county", "monterey hs",
        "el dorado county", "el dorado hills", "folsom", "placerville",
    ],
    "S.CA": [
        "riverside", "john w north", "arlington hs", "poly hs", "pachappa",
        "harrison es", "rcc", "california school for the deaf", "corona",
        "wiltsey", "ramona hs", "castle view", "ontario", "bon view",
        "chino hills", "spectrum center", "jurupa", "eastvale", "harada",
        "monterey park",
        "arizona", "phoenix", "tucson", "mesa", "tempe", "scottsdale",
    ],
}

# Filename hints (standalone tokens first, descriptive keywords second).
STATE_FILE_HINTS = [
    ("albuquerque", "NM"), ("newmexico", "NM"), ("abq", "NM"),
    ("northca", "N.CA"), ("northerncalifornia", "N.CA"),
    ("southca", "S.CA"), ("riverside", "S.CA"), ("arizona", "S.CA"),
    ("alaska", "AK"), ("oregon", "OR"), ("illinois", "IL"),
]
STATE_TOKEN_HINTS = {
    "nm": "NM", "abq": "NM", "nca": "N.CA", "ncal": "N.CA",
    "sca": "S.CA", "scal": "S.CA", "northca": "N.CA", "southca": "S.CA", "ak": "AK", "alaska": "AK",
    "or": "OR", "oregon": "OR", "il": "IL", "illinois": "IL",
}

BASE_DRIVER_STATE = {
    'abdalrahman omer fadlalla': 'N.CA', 'abdelaziz dafi': 'NM',
    'abdelhakem benazouz': 'AK', 'abdul azizi': 'S.CA', 'abdulfatah ali alowdi': 'N.CA',
    'abdulgaleel a albadani': 'N.CA', 'abdullah ahmed eissa': 'N.CA',
    'abdulrahman alnagar alnagar': 'N.CA', 'abeer ahmad dhaifallah': 'N.CA',
    'abla suleiman': 'S.CA', 'adam ait azzat': 'NM', 'adeeb saleh anagar': 'N.CA',
    'adonis gonzalez': 'NM', 'ahmad jaarah': 'S.CA', 'ahmed (mo)': 'AK',
    'ahmed musaad almakkawi': 'N.CA', 'akram awad': 'S.CA', 'alal mohammed bosh': 'N.CA',
    'alamin mohammed y bakor': 'AK', 'alberto ramirez': 'S.CA', 'alexis santos': 'NM',
    'ali adam babeker': 'AK', 'ali saleh hassan': 'N.CA', 'alsadig m mohammed': 'N.CA',
    'ammar alammari': 'N.CA', 'angely wladiuska carrero': 'NM',
    'arette celeste eredia': 'S.CA', 'ashu no last name': 'S.CA',
    'asma mohammed alhamdani': 'N.CA', 'atta ul mohsin': 'S.CA', 'avinash tiwari': 'S.CA',
    'awad ali arbab': 'IL', 'ayman awad': 'NM', 'aziza rayan': 'S.CA',
    'azmi maghathe': 'S.CA', 'bahati basoma': 'AK', 'bassel bahnassi': 'S.CA',
    'brahim bouhamadi': 'NM', 'brahima conde': 'AK', 'christine abrego leyva': 'NM',
    'christopher nicholas rutty': 'AK', 'dana r dbiesi': 'S.CA', 'danier requejo': 'NM',
    'dayanys pie rodriguez': 'NM', 'dehanyi ruiz piti (mo)': 'AK',
    'denakhalil mahmoud al shoukha': 'S.CA', 'denis zamora': 'S.CA',
    'dianelis dr la caridad delgado san juan': 'NM', 'dieumerci chongo (mo)': 'AK',
    'dina farha': 'S.CA', 'ezzat (mo)': 'AK', 'faisal seifou mahamat eltahir': 'AK',
    'fares ameen alshalh': 'N.CA', 'fathi aloui': 'NM', 'fausta piti montero': 'AK',
    'fitsum t tessema': 'NM', 'francisco berrocal camposano': 'AK',
    'franco berrocal camposano': 'AK', 'fuad aleiadih': 'S.CA',
    'gabriel feliz suarez': 'AK', 'habes al tayyeb': 'N.CA',
    'hanan hassan almalahi': 'N.CA', 'hassan mahmoud hassan': 'N.CA',
    'hayat khudhair khalaf': 'AK', 'heba al nser': 'S.CA', 'hesham alrawhani': 'N.CA',
    'hiadar elsayed': 'N.CA', 'himanshu gupta': 'S.CA', 'hiter requejo pena': 'NM',
    'hoda sharaby': 'S.CA', 'husni mubarik': 'N.CA', 'ibrahim m elsayed': 'N.CA',
    'ibrahim mahmoud hassan mohamed': 'N.CA', 'ildephonse tshimpumpu': 'AK',
    'isam qadari': 'N.CA', 'iyad yousef hamdan': 'S.CA', 'james ken puol': 'AK',
    'jennifer soes alizon': 'NM', 'jeremie kitenge katumba': 'AK',
    'jihane benchaouch': 'S.CA', 'jose antonio abreu': 'AK', 'juan fuenmayor': 'NM',
    'judith mutalegwa kizungu': 'IL', 'julio e victoriano': 'AK', 'jumana f naser': 'NM',
    'kevin j machuca': 'AK', 'khalid abu sarriyeh': 'S.CA', 'khalil asfan': 'NM',
    'laith alfayadh': 'S.CA', 'lazaro armentero': 'NM', 'leen albahnassi': 'S.CA',
    'leila hamad rayan': 'S.CA', 'lithe farouk abdullah': 'S.CA', 'lucia c rosendo': 'NM',
    'lulit girma bune': 'N.CA', 'magali de los angeles garcia': 'AK',
    'mandeep singh': 'S.CA', 'mansoor saleh mohammed al ansy': 'AK',
    'maria rivera-ramirez': 'S.CA', 'martin bugere': 'IL',
    'mayelin rives santiesteban': 'NM', 'miriam dawod rayan': 'S.CA',
    'mohamed ahmed hugais': 'N.CA', 'mohamed b ayuob': 'AK',
    'mohamed hussein altayeb abdalla': 'N.CA', 'mohamed omar ali': 'N.CA',
    'mohamed omir': 'N.CA', 'mohammad hamdan ahmad alsutari': 'S.CA',
    'mohammad m al bitari': 'NM', 'mohammed a.i hejab': 'N.CA',
    'mohammed emad bedaer': 'S.CA', 'mohammed h adam': 'N.CA',
    'mohaned abdelazim ahmed elwali': 'N.CA', 'mona bazzoun': 'S.CA',
    'mostafa safwan alhakim': 'S.CA', 'mostafa sharaby': 'S.CA',
    'mubashar b ahmad': 'S.CA', 'muhammad bilal naeem': 'S.CA', 'muhammad laiq': 'N.CA',
    'muhammad obaidul hussain': 'S.CA', 'mustafa ali albarea': 'N.CA',
    'mustafa f m zatar': 'S.CA', 'mustafa hassan abdalkareem': 'N.CA',
    'nabeel aldabbas': 'S.CA', 'nada a suleiman': 'S.CA', 'nafeesa hakimi': 'NM',
    'nagibah e alghazali': 'N.CA', 'najib fettah': 'NM', 'neelam sadiq': 'S.CA',
    'nesrin elshabasy': 'S.CA', 'niazbina joyan': 'NM', 'nihma farha': 'S.CA',
    'niveen mohd abdel aziz abbad': 'S.CA', 'no given name rohit kumar': 'S.CA',
    'nonamegiven sukhvinder': 'S.CA', 'noreldin saddig osaman': 'AK',
    'nour rayyan': 'S.CA', 'omer mustafa': 'N.CA', 'omer omer': 'N.CA',
    'pandasi mugisha': 'AK', 'pedro julio victoriano , (mo)': 'AK',
    'radwan soueidan': 'NM', 'raisa rosendo': 'NM', 'rana muhammad abrar bashir': 'S.CA',
    'rana nazmi abu samrah salaymeh': 'S.CA', 'rasem s alessa': 'NM',
    'rashid masood malik': 'N.CA', 'rehan ahmad malik': 'S.CA',
    'robert luis cabrera ibargoyin': 'NM', 'rodney perez': 'NM',
    'ruben bruno ramirez rivera': 'S.CA', 'safwan alhakim': 'S.CA',
    'saif said awda': 'S.CA', 'salah hassan': 'N.CA', 'salah musa hussein': 'S.CA',
    'salwa saleh anagar': 'N.CA', 'samir m abas': 'N.CA', 'sandeep singh bajwa': 'S.CA',
    'saqib hussain': 'S.CA', 'sarah hamade rayyan': 'S.CA',
    'sheikh shahzaib anwar': 'N.CA', 'siddieg basher khair': 'N.CA',
    'snose omar hamid ali': 'N.CA', 'solomon bekkele': 'N.CA', 'sucad hassan cali': 'N.CA',
    'sukhjit singh': 'S.CA', 'sultan alhalemi': 'N.CA', 'syed saleem ahmad': 'S.CA',
    'tahani hussain': 'S.CA', 'taquia davis': 'S.CA', 'taranjeet singh': 'S.CA',
    'tarek m beltagy': 'NM', 'thaer abusnoubar': 'S.CA', 'wadah alomaisi alomaisi': 'N.CA',
    'wilder antonio montejo arencibia': 'NM', 'xiomara estrellita (mo)': 'AK',
    'yajaira mercedes rodriguez (mo)': 'AK', 'yanina leydinan burgos linares': 'AK',
    'yara fakhrieh jaber': 'S.CA', 'yaremys rodriguez rosendo': 'NM',
    'yasmany carmona luna': 'NM', 'yeshi challa': 'N.CA', 'yoel graveran': 'NM',
    'yosmer armando carrero': 'NM', 'yousef yahya alzawkari': 'N.CA',
    'yuder casanova robles': 'NM', 'zajary laza chapotin': 'NM', 'zeinab ali': 'NM',
    'zohra joyan': 'NM',
}

# Arizona is an operational assignment to S.CA; trips there get region "Arizona (S.CA)".
ARIZONA_CITIES = ["arizona", "phoenix", "tucson", "mesa", "tempe", "scottsdale", "chandler", "glendale az"]
