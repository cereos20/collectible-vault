# Valuation Engine V2 Architectural Blueprint & Engineering Roadmap

> **Authors**: Multi-Agent Engineering Squad
> - **Lead Data Scientist**: Algorithm & Statistical Noise Reduction Expert
> - **Senior API Integration Engineer**: External APIs & Systems Architect
> - **Collectibles Market Expert**: Domain Specialist for Comics, Cards & Collectibles
> 
> **Status**: APPROVED TECHNICAL BLUEPRINT  
> **Target System**: `collectible-vault` Valuation Engine (`app/valuation.py` & `app/services/`)

---

## Executive Summary & Problem Statement

The current `collectible-vault` valuation pipeline fetches sold comp data via the official eBay Browse API. While effective for distinct titles (e.g. *The Amazing Spider-Man #300*), empirical testing reveals critical failure modes:

1. **Short Title Ambiguity False Positives**: Queries with short series titles (e.g., *"52 #38"*, *"Silk #1"*, *"Thor #1"*) pull graphic novel lots, apparel (t-shirts, hoodies), statues, or full 52-issue comic runs ranging from $150–$300 instead of a single $3.00 raw single issue.
2. **Active Listing & Outlier Price Spikes**: Unfiltered outlier comps (e.g. unverified $1,000 asking prices or bulk lot sales) distort median FMV estimates.
3. **Lack of Category Lock & Negative Query Suppression**: General keyword queries frequently match non-media merchandise (toys, keychains, posters).
4. **Single Provider Dependency**: Relying exclusively on raw marketplace keyword searches without domain-specific pricing guide APIs (e.g., PriceCharting / GoCollect) introduces volatility.

**Valuation Engine V2 Objective**: Overhaul the pricing engine by combining category-locked eBay Browse API calls, query negative keyword suppression, PriceCharting multi-tier guide API integration, and an advanced 4-stage statistical outlier rejection pipeline (IQR + Modified Z-Score MAD + 15% Trimmed Median).

---

## 1. API Optimization & Advanced Querying (API Integration Engineer)

### 1.1 Strict Category Locking (`category_ids`)

To prevent cross-category contamination, all external search queries must explicitly declare eBay L1/L2 `category_ids` tailored to the collectible type:

| Collectible Category | Primary eBay Category ID | Description |
| :--- | :--- | :--- |
| **US Comic Books** | `259104` | Collectibles > Comic Books & Memorabilia > American Comics |
| **General Comics** | `63` | Collectibles > Comic Books & Memorabilia |
| **Trading Card Games (TCG)** | `183454` | Toys & Hobbies > CCG/TCG Cards |
| **Non-Sport Trading Cards** | `183050` | Collectibles > Non-Sport Trading Cards |
| **Funko Pops & Vinyl** | `262334` | Toys & Hobbies > Collectible Figures > Funko Pops |
| **Action Figures** | `220` | Toys & Hobbies > Action Figures |

### 1.2 Algorithmic Negative Keyword Suppression

Negative keywords must be dynamically appended to the API search string `q` to filter out non-single-issue or non-media listings:

- **Bulk Lot Suppression**: `-"lot" -"set" -"run" -"collection" -"joblot" -"bundle" -"1-52" -"1-100"`
- **Apparel & Merchandise Suppression**: `-"shirt" -"t-shirt" -"poster" -"statue" -"toy" -"action figure" -"keychain" -"mug" -"hoodie"`
- **Grade Format Filtering**:
  - When evaluating **raw** comics: append `-"cgc" -"cbcs" -"pgx" -"psa" -"bgs" -"sgc"`
  - When evaluating **graded slabs**: explicitly filter for `"cgc"` or `"psa"`
- **Reprint / Digital Suppression**: `-"reprint" -"facsimile" -"digital" -"pdf" -"custom"`

### 1.3 Buying Options & Aspect Filtering

- **Buying Options Filter**: Pass `filter=buyingOptions:{FIXED_PRICE|AUCTION}` to restrict results strictly to completed transactions or fixed-price inventory.
- **Aspect Filtering**: Utilize `aspect_filter` for brand and publisher verification:
  ```http
  aspect_filter=categoryId:259104,aspectName:Publisher,aspectValueName:{Marvel|DC Comics|Image}
  ```

---

## 2. Multi-Market Data Waterfall Architecture (Integration Engineer & Market Expert)

### 2.1 Valuation Waterfall Pipeline

```
                       ┌───────────────────────────────┐
                       │   Item Valuation Request      │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
             ┌──────────────────────────────────────────────────┐
             │ Stage 1: PriceCharting / Guide API Lookup        │
             │ (Structured FMV for raw & CGC 9.8 / PSA 10)      │
             └─────────────────────────┬────────────────────────┘
                                       │ (If 0 comps / no key match)
                                       ▼
             ┌──────────────────────────────────────────────────┐
             │ Stage 2: Category-Locked eBay Browse API         │
             │ (Category ID 259104 + Negative Keywords)          │
             └─────────────────────────┬────────────────────────┘
                                       │ (If 0 comps)
                                       ▼
             ┌──────────────────────────────────────────────────┐
             │ Stage 3: Secondary Broad Title Search            │
             │ (Stripped Volume / Publisher / Variant)          │
             └─────────────────────────┬────────────────────────┘
                                       │ (If 0 comps)
                                       ▼
             ┌──────────────────────────────────────────────────┐
             │ Stage 4: MyComicShop / Baseline Fallback         │
             └──────────────────────────────────────────────────┘
```

### 2.2 PriceCharting API Evaluation

PriceCharting (`pricecharting.com`) provides structured guide pricing for retro games, trading cards (Pokemon, Magic: The Gathering, Sports), and comic books:

- **Search Endpoint**: `GET https://www.pricecharting.com/api/products?t={API_KEY}&q={query}`
- **Product Detail Endpoint**: `GET https://www.pricecharting.com/api/product?t={API_KEY}&id={product_id}`
- **Data Attributes (Values in USD Cents)**:
  - `loose-price`: Raw / Ungraded market value (e.g. $15.00 -> `1500`)
  - `cib-price`: Mid-Grade / Complete-in-Box
  - `graded-price`: High-Grade Slab (CGC 9.8 / PSA 10) (e.g. $250.00 -> `25000`)
  - `volume`: 30-day transaction volume index

---

## 3. Statistical Noise Reduction & Sanitization (Lead Data Scientist)

### 3.1 Short Title Disambiguation & Normalization

Short or purely numeric titles (e.g., *"52"*, *"X-23"*, *"Thor"*) suffer from high query ambiguity. The normalizer enforces context injection:

1. **Title Length Check**: If `len(cleaned_title) <= 3` or title consists of a single generic word:
   - Append `" comic book issue {issue_number}"`
   - Example: Title `"52"`, Issue `"38"` -> Query `"52 comic book issue 38"`
2. **Variant & Volume Stripping**: Strip `"Vol. 1"`, `"Vol. 2"`, publisher names in parentheses, and cover variant letters (`"1H"` -> `"1"`).

### 3.2 4-Stage Statistical Outlier Rejection Pipeline

To eliminate pricing noise from bulk lots or mispriced listings, raw comp price arrays $X = [x_1, x_2, \dots, x_n]$ are processed through four sequential statistical filters:

#### Stage A: Gross Lot Filter
Filter out prices exceeding $3.0 \times \text{median}(X)$ when $\text{median}(X) > 0$.

#### Stage B: Interquartile Range (IQR) Trimming
Calculate 25th percentile ($Q_1$) and 75th percentile ($Q_3$):
$$\text{IQR} = Q_3 - Q_1$$
$$\text{Valid Range} = [Q_1 - 1.5 \times \text{IQR}, \quad Q_3 + 1.5 \times \text{IQR}]$$

#### Stage C: Modified Z-Score Filter (Median Absolute Deviation - MAD)
For non-normally distributed pricing data, calculate Modified Z-scores $M_i$:
$$\text{MAD} = \text{median}(|x_i - \text{median}(X)|)$$
$$M_i = \frac{0.6745 \times |x_i - \text{median}(X)|}{\text{MAD}}$$
Filter out comp prices where $M_i > 3.5$.

#### Stage D: 15% Trimmed Median & Grade Scaling
Sort remaining comps, drop the top 15% and bottom 15% of prices, and calculate the median of the central 70%. Finally, apply condition grade multiplier matrix ($M_{grade}$):
$$\text{FMV}_{final} = \text{median}(\text{Trimmed}(X)) \times M_{grade}$$

---

## 4. Top Recommended Algorithmic Implementations (Python Pseudocode)

### Implementation 1: Advanced Query Disambiguator & Normalizer

```python
import re
from typing import Dict, Any, Optional

def sanitize_and_disambiguate_query(
    title: str,
    category: str = "comic",
    issue_number: Optional[str] = None,
    condition_grade: Optional[str] = None
) -> Dict[str, Any]:
    """
    Normalizes item titles, resolves ultra-short title ambiguity, constructs
    strict category-locked search strings, and appends negative keywords for eBay API V2.
    """
    clean_title = title or ""
    
    # Strip leading "The ", volume numbers, and publisher in parentheses
    clean_title = re.sub(r"^The\s+", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"\bVol\.\s*\d+\b", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"\(.*?\)", "", clean_title)
    clean_title = clean_title.strip()

    # Extract issue number if embedded in title
    issue = issue_number or ""
    if not issue:
        issue_match = re.search(r"#\s*(\d+[a-zA-Z]?)", clean_title)
        if issue_match:
            issue = issue_match.group(1)
            clean_title = re.sub(r"#\s*\d+[a-zA-Z]?", "", clean_title).strip()

    # Normalize issue variant letters (e.g. #1H -> 1)
    if issue:
        issue_num_only = re.sub(r"[a-zA-Z]+$", "", issue)
    else:
        issue_num_only = ""

    # Short Title Disambiguation Engine
    words = clean_title.split()
    is_short_title = len(clean_title) <= 3 or len(words) == 1 or clean_title.isdigit()

    if is_short_title and category.lower() == "comic":
        query_base = f"{clean_title} {issue_num_only} comic book issue".strip()
    elif category.lower() == "comic":
        query_base = f"{clean_title} {issue_num_only} comic".strip()
    elif category.lower() == "trading_card":
        query_base = f"{clean_title} card".strip()
    elif category.lower() == "funko":
        query_base = f"Funko Pop {clean_title}".strip()
    else:
        query_base = f"{clean_title} {issue_num_only}".strip()

    # Category Lock ID Mapping
    category_map = {
        "comic": "259104",        # US Comics
        "trading_card": "183454", # TCG Cards
        "funko": "262334",        # Funko Vinyl
        "figure": "220"           # Action Figures
    }
    category_id = category_map.get(category.lower(), "63")

    # Negative Keyword Exclusions
    negatives = ["-lot", "-set", "-run", "-collection", "-shirt", "-statue", "-toy", "-reprint"]
    
    cond_clean = (condition_grade or "").lower()
    is_graded = any(g in cond_clean for g in ["cgc", "cbcs", "pgx", "psa", "bgs"])
    
    if not is_graded and category.lower() == "comic":
        negatives.extend(["-cgc", "-cbcs", "-pgx"])

    final_query = f"{query_base} {' '.join(negatives)}"

    return {
        "raw_title": title,
        "cleaned_title": clean_title,
        "issue_number": issue_num_only,
        "api_query": final_query,
        "category_id": category_id,
        "is_short_title": is_short_title,
        "is_graded": is_graded
    }
```

---

### Implementation 2: Advanced 4-Stage Outlier Rejection & FMV Pipeline

```python
import statistics
import math
from typing import List, Optional

def calculate_robust_fmv_v2(
    comp_prices: List[float],
    category: str = "comic",
    condition_grade: Optional[str] = None,
    current_val: float = 0.0
) -> float:
    """
    4-Stage Outlier Rejection Pipeline:
    1. Gross Lot Threshold (3x median)
    2. Interquartile Range (IQR 1.5x)
    3. Modified Z-Score / Median Absolute Deviation (MAD > 3.5)
    4. 15% Trimmed Median + Condition Grade Scaling Matrix
    """
    if not comp_prices:
        return 0.0

    prices = sorted([float(p) for p in comp_prices if p > 0])
    if not prices:
        return 0.0

    # STAGE 1: Gross Lot Threshold Filter
    med_raw = statistics.median(prices)
    if med_raw > 0:
        stage1_prices = [p for p in prices if p <= 3.0 * med_raw]
    else:
        stage1_prices = prices

    if not stage1_prices:
        stage1_prices = prices

    # STAGE 2: Interquartile Range (IQR) Trimming
    n = len(stage1_prices)
    if n >= 4:
        q1 = statistics.quantiles(stage1_prices, n=4)[0]
        q3 = statistics.quantiles(stage1_prices, n=4)[2]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        stage2_prices = [p for p in stage1_prices if lower_bound <= p <= upper_bound]
    else:
        stage2_prices = stage1_prices

    if not stage2_prices:
        stage2_prices = stage1_prices

    # STAGE 3: Modified Z-Score Filter (Median Absolute Deviation)
    med_s2 = statistics.median(stage2_prices)
    mad = statistics.median([abs(p - med_s2) for p in stage2_prices])
    
    if mad > 0:
        stage3_prices = []
        for p in stage2_prices:
            mod_z = (0.6745 * abs(p - med_s2)) / mad
            if mod_z <= 3.5:
                stage3_prices.append(p)
    else:
        stage3_prices = stage2_prices

    if not stage3_prices:
        stage3_prices = stage2_prices

    # STAGE 4: 15% Trimmed Median Calculation
    n3 = len(stage3_prices)
    if n3 >= 5:
        trim_count = int(math.floor(n3 * 0.15))
        trimmed_prices = stage3_prices[trim_count : n3 - trim_count]
    else:
        trimmed_prices = stage3_prices

    base_fmv = statistics.median(trimmed_prices)

    # Condition Grade Multiplier Scaling Matrix
    def get_grade_multiplier(grade_str: Optional[str]) -> float:
        if not grade_str:
            return 1.0
        g = str(grade_str).lower()
        if "9.8" in g or "gem" in g:
            return 3.5
        elif "9.6" in g:
            return 2.2
        elif any(k in g for k in ["9.4", "9.2", "9.0", "near mint", "nm"]):
            return 1.4
        elif any(k in g for k in ["8.5", "8.0", "7.5", "7.0", "very fine", "vf"]):
            return 1.0
        elif any(k in g for k in ["6.5", "6.0", "5.5", "5.0", "4.0", "very good", "vg"]):
            return 0.6
        elif any(k in g for k in ["3.5", "3.0", "2.0", "1.0", "fair", "poor"]):
            return 0.3
        return 1.0

    cond_clean = (condition_grade or "").lower()
    is_graded = any(kw in cond_clean for kw in ["cgc", "cbcs", "pgx", "psa", "bgs"])

    if category.lower() == "comic" and not is_graded:
        multiplier = get_grade_multiplier(condition_grade)
        base_fmv = base_fmv * multiplier

    # Cap sudden growth relative to existing low valuation
    if base_fmv > 30.0 and 0.0 < current_val <= 30.0:
        base_fmv = min(base_fmv, max(30.0, current_val * 1.25))

    return round(base_fmv, 2)
```

---

## 5. Implementation Milestones & Roadmap

| Phase | Milestone | Focus Area | Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Short Title Normalization & Category Locks | `app/valuation.py` | Implement `sanitize_and_disambiguate_query()`, category ID locks (259104, 183454), and negative keyword strings. |
| **Phase 2** | Statistical Outlier Rejection V2 | `app/valuation.py` | Integrate 4-stage outlier pipeline (IQR + Modified Z-Score MAD + 15% Trimmed Median). |
| **Phase 3** | PriceCharting Guide API Fallback | `app/services/pricecharting.py` | Build standalone client for PriceCharting API integration as Stage 1 Waterfall guide price. |
| **Phase 4** | Automated Regression Test Suite | `tests/test_valuation_v2.py` | Unit tests for short titles ("52 #38", "Silk #1"), outlier arrays, and PriceCharting mock responses. |
