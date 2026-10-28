"""Generate FAKE auction data for development. Not real Manheim data."""
import random
from datetime import date, timedelta

import pandas as pd

VEHICLES = {  # make, model: (base MMR, demand trend per week, base sell-through)
    ("Toyota", "Camry"): (19000, 0.010, 0.72),
    ("Toyota", "RAV4"): (24000, 0.030, 0.78),
    ("Honda", "CR-V"): (23000, 0.025, 0.75),
    ("Honda", "Civic"): (17000, 0.005, 0.70),
    ("Ford", "F-150"): (31000, 0.008, 0.68),
    ("Chevrolet", "Silverado 1500"): (30000, -0.010, 0.62),
    ("Nissan", "Altima"): (14000, -0.025, 0.52),
    ("Tesla", "Model 3"): (23000, -0.030, 0.48),
    ("Jeep", "Grand Cherokee"): (25000, 0.000, 0.60),
    ("Hyundai", "Tucson"): (20000, 0.015, 0.66),
}
REGIONS = ["Southeast", "Northeast", "Midwest", "Southwest", "West"]


def main(weeks: int = 16, seed: int = 7) -> None:
    rnd = random.Random(seed)
    start = date(2026, 7, 1)
    rows = []
    for (make, model), (mmr0, drift, st0) in VEHICLES.items():
        for day in range(weeks * 7):
            week = day / 7
            demand = 1 + drift * week
            for _ in range(rnd.randint(0, int(4 * demand) + 1)):
                year = rnd.randint(2017, 2024)
                miles = max(3000, int(rnd.gauss((2026 - year) * 13000, 9000)))
                grade = round(min(5.0, max(1.0, rnd.gauss(3.4, 0.7))), 1)
                mmr = mmr0 * demand * (1 - 0.06 * (2024 - year)) * (1 + 0.05 * (grade - 3.4))
                sold = rnd.random() < min(0.95, st0 + drift * week + 0.05 * (grade - 3.4))
                price = round(mmr * rnd.gauss(1.0 + drift * 3, 0.04), -1) if sold else None
                rows.append({
                    "sale_date": start + timedelta(days=day), "year": year, "make": make,
                    "model": model, "mileage": miles, "condition_grade": grade,
                    "region": rnd.choice(REGIONS), "mmr": round(mmr, -1),
                    "sale_price": price, "sold": sold,
                })
    pd.DataFrame(rows).to_csv("data/sample_sales.csv", index=False)
    print(f"wrote {len(rows)} rows to data/sample_sales.csv")


if __name__ == "__main__":
    main()
