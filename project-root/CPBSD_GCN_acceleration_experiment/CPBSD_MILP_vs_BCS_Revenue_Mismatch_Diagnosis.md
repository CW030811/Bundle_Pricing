# CPBSD-MILP vs BCS Revenue Mismatch Diagnosis

## 1. What the Diagnosis Code Compares

The diagnostic script compares two things under the **same pricing solution** (p*, d*):

1. MILP solution output
   - The bundle chosen by the MILP decision variables x_{kns}, y_{ks}
   - Revenue computed from that bundle

2. BCS evaluator result
   - The bundle returned by the bcs_choice() function that solves the customer's self-selection problem

The BCS function:

- Computes utility  
  u_{kn}(s) = v_{kn} - p_n + d_s
- Selects the top‑s products for each bundle size s
- Chooses the s that maximizes surplus

However, the evaluator only updates the best choice when

    surplus > best_surplus

so it does not explicitly handle ties (equal surplus bundles).

---

# 2. Two Types of Observed Differences

From the result file, the mismatch cases fall into two categories.

---

# A. Equal Surplus but Different Bundles (Tie Case)

Example:

MILP
s = 4  
surplus = 0.259046  
revenue = 1.871270  

BCS
s = 3  
surplus = 0.259046  
revenue = 1.687297  

Interpretation:

- Both bundles give exactly the same customer surplus
- Therefore both satisfy surplus maximization
- MILP selects the bundle giving higher seller revenue

This occurs because:

- the MILP objective maximizes seller profit
- when multiple bundles give the same surplus, MILP may choose the one with higher revenue

This behavior is called optimistic tie-breaking in bilevel optimization.

Result:

Surplus equality confirms the BCS optimality constraints are tight.

Revenue differences are expected under ties.

---

# B. Zero Surplus Tie Between Buying and Outside Option

Example:

MILP  
s = 3  
surplus = 0  
revenue = 2.511429  

BCS evaluator  
s = 0  
surplus = 0  
revenue = 0  

Interpretation:

- The bundle and the outside option both give surplus = 0
- They are therefore both optimal for the customer

However:

- MILP selects the bundle (positive revenue)
- The BCS evaluator selects the outside option because the code returns empty when

    best_surplus <= 1e-9

Thus the difference is again due to tie-breaking assumptions.

---

# 3. Is This a Formulation Error?

No.

The CPBSD-MILP formulation ensures:

- customers cannot choose a bundle with strictly lower surplus

Your results show that:

- MILP surplus = BCS surplus in tie cases

Therefore:

The optimality constraints are working correctly.

The mismatch occurs because the model does not explicitly define how customers break ties.

---

# 4. Is Big-M the Cause?

Very unlikely.

Typical Big-M errors would cause:

- incorrect q values
- incorrect surplus comparisons
- customers choosing strictly worse bundles

But your diagnostics show:

- identical surplus values between MILP and BCS in mismatch cases

This strongly indicates that Big-M linearization is functioning correctly.

---

# 5. Interpretation in Bilevel Optimization

Your MILP implicitly assumes:

Optimistic tie-breaking

When multiple bundles maximize surplus, the customer selects the one maximizing seller profit.

Your BCS evaluator assumes:

Pessimistic tie-breaking

When surplus is zero, the customer chooses the outside option.

Because of this mismatch:

MILP revenue ≠ BCS revenue.

---

# 6. How to Align the Two Evaluations

## Option A (Recommended for Diagnostics)

Modify the BCS evaluator:

1. Enumerate all bundles achieving the maximum surplus
2. Among them choose the bundle with maximum seller revenue

This reproduces the MILP tie-breaking rule.

---

## Option B (Model Outside Option Preference)

If the intended behavior is:

customers choose the outside option when surplus = 0

Then the MILP must enforce

w_k >= epsilon * sum_s y_{ks}

This forces positive surplus whenever a bundle is chosen.

Note:

- This slightly modifies the original model
- Requires a small epsilon

---

# 7. Final Conclusion

Your experiment demonstrates:

1. Customer optimality constraints are tight
2. Revenue differences arise from tie-breaking
3. The CPBSD-MILP formulation is not necessarily incorrect
4. Big-M is unlikely to be the cause

The discrepancy is explained by different assumptions about how customers break ties between bundles with equal surplus.
