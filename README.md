# Railroad Blocking Optimization: A Two-Yard Case Study

## Project Overview
This project develops a mathematical optimization model for a restricted two-yard Railroad Blocking Problem using Python, Pyomo, and Gurobi.

The model determines whether to open a freight block and how many railcars to serve while considering fixed block-opening costs, transportation costs, unserved-demand penalties, and operational capacity constraints.

## Problem Scope
The case study considers:
- Origin Yard: 10650 – South Plainfield
- Destination Yard: 10641 – Poinier Street
- Demand: 2,429 merchandise railcars
- Selected route distance: 16.3966 miles
- Minimum block volume: 350 railcars

## Mathematical Model
The objective is to minimise:

Min Z = 2500y + 16.396637x + 20u

Where:
- y = Binary variable indicating whether the block is opened
- x = Number of railcars served
- u = Number of railcars left unserved

The model includes demand balance, block-opening dependency, minimum block volume, yard capacity, and physical link capacity constraints.

The unserved-demand penalty of $20 per railcar is a scenario assumption.

## Technologies Used
- Python
- Pandas
- Pyomo
- Gurobi Optimizer
- VS Code

## Results
For the selected scenario, the model returns:
- Block opened: Yes
- Freight served: 2,429 railcars
- Unserved demand: 0
- Demand fulfillment: 100%
- Total cost: $42,327.43

## How to Run
1. Install Python.
2. Install the required packages:

   pip install pandas pyomo gurobipy

3. Keep the Python script and all four CSV files in the same folder.
4. Run:

   python railroad_blocking_open_close_fixed.py

A working Gurobi installation and valid license are required.

## Project Limitations
This is a restricted two-yard case study, not a complete solution to the full national railroad blocking problem. The physical route is manually selected and validated rather than optimised among alternative routes. The $20 unserved-demand penalty is an assumed scenario parameter.

## Data
The CSV files represent the railway network, demand, and model settings used in this case study. Refer to the original competition data source and its terms for dataset attribution and redistribution permissions.
