"""
Adds two new columns to the Listener dataset, without touching existing data:

- Channel: which conversation channel this record came from. All current
  records are "Chat" (that's the only channel we've built so far). Future
  email/call records will use their own value here — no structure change
  needed later.

- Customer_ID: an anonymized, synthetic customer identifier (e.g. CUST-0247).
  Assigned from a fixed pool so some customers naturally repeat across
  sessions — this lets the dashboard show "customers with repeat issues"
  without storing any real identity.

Run this once against the current dataset file. It creates a new file
(does not overwrite the original), so you can compare before/after.
"""

import pandas as pd
import numpy as np

INPUT_FILE = "OLT_Listener_Synthetic_Dataset_v2.xlsx"
OUTPUT_FILE = "OLT_Listener_Synthetic_Dataset_v3.xlsx"

# Fixed seed = reproducible assignment (same customer IDs every time you run it)
rng = np.random.default_rng(42)

df = pd.read_excel(INPUT_FILE)

# 1. Channel — all existing data is from the chat channel
df["Channel"] = "Chat"

# 2. Customer_ID — synthetic pool of ~400 customers, so some naturally repeat
NUM_SYNTHETIC_CUSTOMERS = 400
customer_pool = [f"CUST-{i:04d}" for i in range(1, NUM_SYNTHETIC_CUSTOMERS + 1)]
df["Customer_ID"] = rng.choice(customer_pool, size=len(df))

df.to_excel(OUTPUT_FILE, index=False)

print(f"Done. Wrote {len(df)} rows with new columns to {OUTPUT_FILE}")
print(f"Columns now: {df.columns.tolist()}")
print(f"Unique customers used: {df['Customer_ID'].nunique()}")
