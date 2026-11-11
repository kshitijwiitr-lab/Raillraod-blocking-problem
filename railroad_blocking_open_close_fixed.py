import os
import pandas as pd
import pyomo.environ as pyo

# Always load CSV files from the folder containing this Python script.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# RAILROAD BLOCKING: TWO-YARD OPEN/CLOSE MODEL
# Pyomo + Gurobi
#
# Data files expected in the same folder as this script:
# node.csv, link.csv, demand.csv, setting.csv
#
# Important modelling extension:
# The competition data does not provide a monetary penalty for
# unserved demand. This script asks the user to enter one.
# The default $20/car is an illustrative scenario assumption,
# NOT an official competition parameter.
# ============================================================


# -----------------------------
# 1. LOAD DATA
# -----------------------------

node_path = os.path.join(BASE_DIR, "node.csv")
link_path = os.path.join(BASE_DIR, "link.csv")
demand_path = os.path.join(BASE_DIR, "demand.csv")
setting_path = os.path.join(BASE_DIR, "setting.csv")

required_files = [node_path, link_path, demand_path, setting_path]
missing_files = [os.path.basename(path) for path in required_files if not os.path.isfile(path)]

if missing_files:
    raise FileNotFoundError(
        "The following CSV file(s) were not found in the script folder "
        f"({BASE_DIR}): {', '.join(missing_files)}. "
        "Place all four CSV files in the same folder as this Python script."
    )

node = pd.read_csv(node_path)
link = pd.read_csv(link_path)
demand = pd.read_csv(demand_path)
setting = pd.read_csv(setting_path)

print("Dataset loaded successfully.")
print("Node rows:", len(node))
print("Link rows:", len(link))
print("Demand rows:", len(demand))

# Normalize ID columns so comparisons work consistently.
for df, columns in [
    (node, ["node_id"]),
    (link, ["link_id", "from_node_id", "to_node_id"]),
    (demand, ["origin_yard_id", "dest_yard_id"]),
]:
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="raise").astype("int64")


# -----------------------------
# 2. READ SETTINGS
# -----------------------------

settings = dict(
    zip(
        setting["parameter"].astype(str).str.strip(),
        setting["value"]
    )
)

def get_setting(parameter):
    if parameter not in settings:
        raise KeyError(f"Missing parameter in setting.csv: {parameter}")
    return float(settings[parameter])

fixed_block_cost = get_setting("block_fixed_cost")
transport_cost_per_car_mile = get_setting(
    "transport_cost_coefficient"
)
interchange_cost_per_car = get_setting("interchange_cost")


# -----------------------------
# 3. SELECT THE TWO YARDS
# -----------------------------

print("\n========== SELECT YARDS ==========")

origin_yard_id = int(input("Enter Origin Yard ID: ").strip())
destination_yard_id = int(input("Enter Destination Yard ID: ").strip())

if origin_yard_id == destination_yard_id:
    raise ValueError("Origin and destination yards must be different.")

selected_demand = demand[
    (demand["origin_yard_id"] == origin_yard_id) &
    (demand["dest_yard_id"] == destination_yard_id)
].copy()

if selected_demand.empty:
    raise ValueError("No demand record exists for this yard pair.")

print("\nSelected Demand Records:")
print(selected_demand.to_string(index=False))

# This demonstration selects one block type at a time.
block_types = selected_demand["block_type"].dropna().unique()

if len(block_types) != 1:
    raise ValueError(
        "This yard pair has multiple block types. "
        "Select a pair with one block type, or extend the model "
        "to model separate blocks by commodity."
    )

selected_block_type = str(block_types[0])
total_demand = float(selected_demand["volume"].sum())

if total_demand <= 0 or not total_demand.is_integer():
    raise ValueError(
        "This script expects positive whole-number railcar demand."
    )

total_demand = int(total_demand)

print("\nSelected Block Type:", selected_block_type)
print("Total Freight Demand:", total_demand, "railcars")


# -----------------------------
# 4. GET YARD DATA
# -----------------------------

origin_rows = node[node["node_id"] == origin_yard_id]
destination_rows = node[node["node_id"] == destination_yard_id]

if origin_rows.empty or destination_rows.empty:
    raise ValueError("Origin or destination yard ID was not found in node.csv.")

origin = origin_rows.iloc[0]
destination = destination_rows.iloc[0]

if str(origin["node_type"]).lower() != "yard":
    raise ValueError("Origin node is not classified as a yard.")

if str(destination["node_type"]).lower() != "yard":
    raise ValueError("Destination node is not classified as a yard.")

origin_capacity = float(origin["handling_capacity"])
destination_capacity = float(destination["handling_capacity"])

# Check that both yards permit the selected block type.
commodity = selected_block_type.strip().lower()

origin_commodities = [
    x.strip().lower()
    for x in str(origin["allowed_commodities"]).split(",")
]
destination_commodities = [
    x.strip().lower()
    for x in str(destination["allowed_commodities"]).split(",")
]

if commodity not in origin_commodities:
    raise ValueError("Origin yard does not permit this block type.")

if commodity not in destination_commodities:
    raise ValueError("Destination yard does not permit this block type.")

different_railroads = (
    str(origin["railroad_id"]) != str(destination["railroad_id"])
)


# -----------------------------
# 5. SELECT AND VERIFY PHYSICAL ROUTE
# -----------------------------

print("\n========== SELECT PHYSICAL ROUTE ==========")
print("Enter the link IDs connecting origin to destination.")
print("Enter them in the correct travel order.")
print("Example: 101, 205, 310")

route_input = input("Enter Route Link IDs: ").strip()

route_ids = [
    int(value.strip())
    for value in route_input.split(",")
    if value.strip()
]

if not route_ids:
    raise ValueError("At least one route link ID is required.")

if len(route_ids) != len(set(route_ids)):
    raise ValueError("Duplicate link IDs were entered.")

route = link[link["link_id"].isin(route_ids)].copy()

if len(route) != len(route_ids):
    found_ids = set(route["link_id"].tolist())
    missing_ids = [rid for rid in route_ids if rid not in found_ids]
    raise ValueError(f"These route link IDs were not found: {missing_ids}")

route_order = {link_id: i for i, link_id in enumerate(route_ids)}
route["route_order"] = route["link_id"].map(route_order)
route = route.sort_values("route_order").reset_index(drop=True)

# Verify that each link connects to the next link.
for i in range(len(route) - 1):
    current_to = int(route.loc[i, "to_node_id"])
    next_from = int(route.loc[i + 1, "from_node_id"])

    if current_to != next_from:
        raise ValueError(
            f"Route is not continuous between link "
            f"{int(route.loc[i, 'link_id'])} and "
            f"{int(route.loc[i + 1, 'link_id'])}."
        )

# Verify origin and destination.
if int(route.iloc[0]["from_node_id"]) != origin_yard_id:
    raise ValueError("First route link does not start at the origin yard.")

if int(route.iloc[-1]["to_node_id"]) != destination_yard_id:
    raise ValueError("Last route link does not end at the destination yard.")

route_distance = float(route["length"].sum())
minimum_link_capacity = float(route["capacity"].min())

print("\nSelected Route:")
print(
    route[
        ["link_id", "from_node_id", "to_node_id", "length", "capacity"]
    ].to_string(index=False)
)

print("\nTotal Route Distance:", route_distance, "miles")


# -----------------------------
# 6. MINIMUM BLOCK VOLUME
# -----------------------------

if route_distance < 100:
    minimum_block_volume = get_setting("min_block_vol_short(<100mi)")
elif route_distance <= 500:
    minimum_block_volume = get_setting("min_block_vol_med(100-500mi)")
else:
    minimum_block_volume = get_setting("min_block_vol_long(>500mi)")

print("\n========== MODEL PARAMETERS ==========")
print("Fixed Block Cost: $", fixed_block_cost)
print("Transport Cost Coefficient: $", transport_cost_per_car_mile)
print("Interchange Cost: $", interchange_cost_per_car)
print("Minimum Block Volume:", minimum_block_volume)


# -----------------------------
# 7. UN-SERVED DEMAND PENALTY
# -----------------------------

print("\n========== OPEN/CLOSE DECISION ==========")
print(
    "The dataset does not provide a monetary penalty for "
    "unserved freight."
)
print(
    "Enter a penalty per unserved railcar. This is a scenario "
    "assumption, not an official dataset value."
)

penalty_text = input(
    "Penalty per unserved railcar in dollars [default = 20]: "
).strip()

if penalty_text == "":
    unserved_penalty = 20.0
else:
    unserved_penalty = float(penalty_text)

if unserved_penalty < 0:
    raise ValueError("Unserved-demand penalty cannot be negative.")

# Per-car cost of serving freight through this route.
transport_cost_per_car = (
    transport_cost_per_car_mile * route_distance
)

if different_railroads:
    transport_cost_per_car += interchange_cost_per_car

# Break-even penalty: above this value, serving all demand
# through the block costs less than leaving all demand unserved.
break_even_penalty = (
    transport_cost_per_car
    + fixed_block_cost / total_demand
)

print("\nTransport cost per served railcar: $",
      round(transport_cost_per_car, 4))
print("Break-even unserved penalty per railcar: $",
      round(break_even_penalty, 4))
print("Penalty used in this scenario: $", unserved_penalty)


# -----------------------------
# 8. BUILD PYOMO MODEL
# -----------------------------

model = pyo.ConcreteModel()

# y = 1 if the block is opened; 0 otherwise.
model.open_block = pyo.Var(within=pyo.Binary)

# Integer number of railcars transported through the block.
model.freight = pyo.Var(within=pyo.NonNegativeIntegers)

# Integer number of railcars whose demand is not served.
model.unserved = pyo.Var(within=pyo.NonNegativeIntegers)


# -----------------------------
# 9. OBJECTIVE FUNCTION
# -----------------------------

# Total cost =
# fixed block cost
# + transportation cost for served railcars
# + interchange cost (if applicable)
# + penalty for unserved railcars.

model.total_cost = pyo.Objective(
    expr=(
        fixed_block_cost * model.open_block
        + transport_cost_per_car * model.freight
        + unserved_penalty * model.unserved
    ),
    sense=pyo.minimize
)


# -----------------------------
# 10. CONSTRAINTS
# -----------------------------

# (1) Demand balance:
# Every demanded railcar is either served or unserved.
model.demand_balance = pyo.Constraint(
    expr=model.freight + model.unserved == total_demand
)

# (2) Freight can be transported only if the block is open.
model.block_opening = pyo.Constraint(
    expr=model.freight <= total_demand * model.open_block
)

# (3) If the block is opened, it must meet minimum block volume.
model.minimum_block_volume = pyo.Constraint(
    expr=model.freight >= minimum_block_volume * model.open_block
)

# (4) Origin yard capacity.
model.origin_capacity = pyo.Constraint(
    expr=model.freight <= origin_capacity
)

# (5) Destination yard capacity.
model.destination_capacity = pyo.Constraint(
    expr=model.freight <= destination_capacity
)

# (6) Every physical link on the route must have sufficient capacity.
model.link_capacity = pyo.ConstraintList()

for _, row in route.iterrows():
    model.link_capacity.add(
        model.freight <= float(row["capacity"])
    )


# -----------------------------
# 11. SOLVE USING GUROBI
# -----------------------------

print("\n========== STARTING GUROBI SOLVER ==========")

solver = pyo.SolverFactory("gurobi")

if not solver.available():
    raise RuntimeError(
        "Gurobi is unavailable. Check your installation and license."
    )

results = solver.solve(model, tee=True)

status = results.solver.termination_condition


# -----------------------------
# 12. DISPLAY RESULTS
# -----------------------------

print("\n")
print("=" * 60)
print("       RAILROAD BLOCKING OPTIMIZATION RESULTS")
print("=" * 60)

print("Solver termination condition:", status)

if status == pyo.TerminationCondition.optimal:

    block_open = int(round(pyo.value(model.open_block)))
    freight_served = int(round(pyo.value(model.freight)))
    freight_unserved = int(round(pyo.value(model.unserved)))
    total_cost = float(pyo.value(model.total_cost))

    fixed_component = fixed_block_cost * block_open
    transport_component = transport_cost_per_car * freight_served
    unserved_component = unserved_penalty * freight_unserved

    print("\nSELECTED YARDS")
    print("Origin:", origin_yard_id, "-", origin["name"])
    print("Destination:", destination_yard_id, "-", destination["name"])
    print("Block Type:", selected_block_type)

    print("\nBLOCK DECISION")
    print("Block Opened:", "YES" if block_open == 1 else "NO")

    print("\nFREIGHT ALLOCATION")
    print("Total Demand:", total_demand, "railcars")
    print("Freight Served:", freight_served, "railcars")
    print("Freight Unserved:", freight_unserved, "railcars")
    print(
        "Demand Fulfilment:",
        round(100 * freight_served / total_demand, 2),
        "%"
    )

    print("\nCAPACITY CHECKS")
    print("Minimum Block Volume:", minimum_block_volume)
    print("Origin Yard Capacity:", origin_capacity)
    print("Destination Yard Capacity:", destination_capacity)
    print("Minimum Physical-Link Capacity:", minimum_link_capacity)

    print("\nROUTE INFORMATION")
    print("Number of Physical Links:", len(route))
    print("Route Distance:", route_distance, "miles")

    print("\nCOST BREAKDOWN")
    print("Fixed Block Cost: $", round(fixed_component, 2))
    print("Transportation + Interchange Cost: $",
          round(transport_component, 2))
    print("Unserved-Demand Penalty: $",
          round(unserved_component, 2))
    print("-" * 45)
    print("TOTAL MODEL COST: $", round(total_cost, 2))

    print("\nFEASIBILITY CHECKS")
    if block_open == 1:
        print(
            "Minimum block volume satisfied:",
            freight_served >= minimum_block_volume
        )
    else:
        print("Block closed; minimum block volume is not applicable.")

    print(
        "Origin capacity respected:",
        freight_served <= origin_capacity
    )
    print(
        "Destination capacity respected:",
        freight_served <= destination_capacity
    )
    print(
        "All physical-link capacities respected:",
        all(
            freight_served <= float(capacity)
            for capacity in route["capacity"]
        )
    )

    print("\nDECISION INTERPRETATION")
    if block_open == 1:
        print(
            "Opening the block is economical under the selected "
            "unserved-demand penalty."
        )
    else:
        print(
            "Closing the block is economical under the selected "
            "unserved-demand penalty. All demand remains unserved "
            "in this two-option model."
        )

    print(
        "\nNote: The unserved-demand penalty is a user-entered "
        "scenario assumption, not a value supplied in setting.csv."
    )

elif status == pyo.TerminationCondition.infeasible:

    print("\nThe model is infeasible.")
    print(
        "Check demand, minimum block volume, yard capacities "
        "and physical-link capacities."
    )

else:
    print("\nSolver did not return an optimal solution.")
    print("Termination condition:", status)

print("\n" + "=" * 60)
