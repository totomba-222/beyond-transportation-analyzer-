"""Driver pay NEGOTIATED with a driver (approved by management). Edit this list: a trip that matches an entry is NOT a difference
for the state manager; it is shown in its own category ("Negotiated with the driver") so management still sees the amount.
Each entry: (state, driver, route, pay, note)
  state  : "S.CA", "N.CA", "OR", ... or "*" for any state
  driver : driver name (any capitalisation / spacing)
  route  : route as written in the First report ('Redwood HS OB 01'; IB/OB, (W) and _A suffixes are ignored), or "*" for every route of the driver
  pay    : the agreed pay per trip, or None = any pay
  note   : who approved / why (shown in the report)
"""
NEGOTIATED = [
    # ("N.CA", "Abdulrahman Alnagar Alnagar", "Redwood HS OB 01", 50.0, "agreed with N.CA manager"),
    # driver "*" = any driver on that route. Entries below come from the N.CA manager's explanation (Nov 24) - delete a line if it is wrong.
    ("N.CA", "*", "Bayhill HS IB 02", None, "Per N.CA manager, confirmed Nov 24 - Richmond, Asma's trip: far, nobody accepted it (confirm route)"),
    ("N.CA", "*", "Bayhill HS OB 02", None, "Per N.CA manager, confirmed Nov 24 - Richmond, Asma's trip: far, nobody accepted it (confirm route)"),
    ("N.CA", "Mohamed Ahmed Hugais", "Sierra of Solano County IB 03", None, "Per N.CA manager, confirmed Nov 24 - Benicia, the trip no other driver accepted (confirm route)"),
    ("N.CA", "Mohamed Ahmed Hugais", "Sierra of Solano County OB 03", None, "Per N.CA manager, confirmed Nov 24 - Benicia, the trip no other driver accepted (confirm route)"),
]
