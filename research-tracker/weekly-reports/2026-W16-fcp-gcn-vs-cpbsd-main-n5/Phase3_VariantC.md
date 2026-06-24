# Hybrid Bundle Pricing Formulation with Fixed Candidate Prices

## 1. Sets

- \(N\): product set, with \(|N|=n\)
- \(\mathcal{B}=2^N\setminus\{\varnothing\}\): bundle universe  
  若实际不是在 full bundle space 上求解，而是在某个工作 bundle space 上求解，只需将 \(\mathcal{B}\) 替换为对应工作空间
- \(F\subseteq \mathcal{B}\): priced candidate bundle set, with fixed prices \(P_F(b)\)
- \(K\): customer set
- \(S=\{1,\dots,n\}\): bundle-size set

对任意 \(b\in\mathcal{B}\)，记 \(|b|\) 为 bundle size。

---

## 2. Canonical Split Set (Avoiding Duplicate Constraints)

对任意 \(b\in\mathcal{B}\)，定义其所有非空二拆分：

\[
\Pi(b):=\{(b_1,b_2)\mid b_1\cap b_2=\varnothing,\; b_1\cup b_2=b,\; b_1\neq\varnothing,\; b_2\neq\varnothing\}.
\]

为了避免 \((b_1,b_2)\) 与 \((b_2,b_1)\) 重复，定义 canonical split set：

\[
\Pi^\star(b):=
\left\{
(b_1,b_2)\in \Pi(b)\; \middle| \;
|b_1|<|b_2|
\;\text{or}\;
\big(|b_1|=|b_2| \text{ and } b_1 \prec_{\mathrm{lex}} b_2\big)
\right\}.
\]

其中 \( \prec_{\mathrm{lex}} \) 表示在固定产品顺序下的字典序。

对 non-\(F\) 部分保留的 **强版本 size-level 次可加**，也采用去重规则：

\[
\mathcal T := \{(s_1,s_2,s)\mid s_1,s_2,s\in S,\; s_1+s_2=s,\; s_1\le s_2\}.
\]

---

## 3. Parameters

- \(P_F(b)\), \(\forall b\in F\): fixed price of candidate bundle \(b\)
- \(v_k(b)\), \(\forall k\in K,\forall b\in\mathcal{B}\): valuation of customer \(k\) for bundle \(b\)
- \(c_b\), \(\forall b\in\mathcal{B}\): cost of bundle \(b\)  
  若需要客户相关成本，可替换为 \(c_{kb}\)
- \(\bar p_s\), \(\forall s\in S\): valid upper bound of size-\(s\) BSP price
- \(\bar q_b\), \(\forall b\in\mathcal{B}\): valid upper bound of bundle price, defined by

\[
\bar q_b=
\begin{cases}
P_F(b), & b\in F,\\
\bar p_{|b|}, & b\notin F
\end{cases}
\]

- \(M_k\): sufficiently large Big-M constant for customer \(k\)

---

## 4. Decision Variables

### Pricing variables

- \(p_s \ge 0\), \(\forall s\in S\): size-based price applied to all bundles not in \(F\)
- \(q_b \ge 0\), \(\forall b\in\mathcal{B}\): final hybrid price of bundle \(b\)

### Choice / payment variables

- \(x_{kb}\in\{0,1\}\), \(\forall k\in K,\forall b\in\mathcal{B}\): equals 1 if customer \(k\) purchases bundle \(b\)
- \(r_{kb}\ge 0\), \(\forall k\in K,\forall b\in\mathcal{B}\): payment made by customer \(k\) for bundle \(b\)

---

## 5. Objective

最大化平均利润：

\[
\max \;\; \frac{1}{|K|}\sum_{k\in K}\sum_{b\in\mathcal{B}}\big(r_{kb}-c_b x_{kb}\big)
\]

若采用客户相关成本，则替换为：

\[
\max \;\; \frac{1}{|K|}\sum_{k\in K}\sum_{b\in\mathcal{B}}\big(r_{kb}-c_{kb} x_{kb}\big)
\]

---

## 6. Hybrid Price Linking Constraints

### (H1) Fixed candidate prices are preserved

\[
q_b = P_F(b), \qquad \forall b\in F
\]

### (H2) Non-\(F\) bundles share size-based prices

\[
q_b = p_{|b|}, \qquad \forall b\in \mathcal{B}\setminus F
\]

因此最终价格函数为：

\[
q_b=
\begin{cases}
P_F(b), & b\in F,\\
p_{|b|}, & b\notin F
\end{cases}
\]

---

## 7. Customer Choice Constraints

### (C1) Each customer buys at most one bundle

\[
\sum_{b\in\mathcal{B}} x_{kb}\le 1, \qquad \forall k\in K
\]

### (C2) If bundle \(b\) is chosen, it must yield nonnegative utility

\[
v_k(b)-q_b \ge -M_k(1-x_{kb}),
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

当 \(x_{kb}=1\) 时，上式变为：

\[
v_k(b)-q_b \ge 0
\]

### (C3) If bundle \(b\) is chosen, it must weakly dominate every other bundle

\[
v_k(b)-q_b
\ge
v_k(b')-q_{b'} - M_k(1-x_{kb}),
\qquad
\forall k\in K,\forall b,b'\in\mathcal{B},\; b'\neq b
\]

当 \(x_{kb}=1\) 时，上式变为：

\[
v_k(b)-q_b \ge v_k(b')-q_{b'},\qquad \forall b'\neq b
\]

即被选中的 bundle 必须是客户在当前 hybrid menu 下的最优选择之一。

---

## 8. Payment Linearization Constraints

为了线性化：

\[
r_{kb}=q_b x_{kb}
\]

加入如下约束。

### (P1)

\[
r_{kb}\le q_b,
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

### (P2)

\[
r_{kb}\le \bar q_b x_{kb},
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

### (P3)

\[
r_{kb}\ge q_b-\bar q_b(1-x_{kb}),
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

### (P4)

\[
r_{kb}\ge 0,
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

因此：

- 当 \(x_{kb}=1\) 时，\(r_{kb}=q_b\)
- 当 \(x_{kb}=0\) 时，\(r_{kb}=0\)

---

## 9. Hybrid Subadditivity Constraints

本 formulation 中：

- **不保留全局单调性约束**
- **保留 non-\(F\) 部分的强版本 size-level 次可加**
- **补上所有涉及 \(F\) 的 hybrid 次可加**
- **不再重复加入 \(b,b_1,b_2\in F\) 的次可加，因为 \(P_F\) 已知满足**

### (S1) Strong size-level subadditivity on the non-\(F\) side

\[
p_s \le p_{s_1}+p_{s_2},
\qquad
\forall (s_1,s_2,s)\in \mathcal T
\]

即：

\[
p_s \le p_{s_1}+p_{s_2},
\qquad
\forall s_1,s_2,s\in S:\; s_1+s_2=s,\; s_1\le s_2
\]

这对应 non-\(F\) 情形下保留的强版本 Case 1。

---

### (S2) Mixed / fixed-parent hybrid subadditivity

对所有 **不是 FFF，也不是 NNN** 的 canonical split，统一施加：

\[
q_b \le q_{b_1}+q_{b_2},
\qquad
\forall b\in\mathcal{B},\;
\forall (b_1,b_2)\in \Pi^\star(b)
\]

满足以下条件：

\[
\big( b\in F \;\vee\; b_1\in F \;\vee\; b_2\in F \big)
\]

且

\[
\neg\big( b\in F \wedge b_1\in F \wedge b_2\in F \big)
\]

这条统一约束覆盖以下所有必要情形：

1. \(b\in F,\; b_1,b_2\notin F\)
2. \(b\in F\)，且 \(b_1,b_2\) 中一个在 \(F\)、一个不在 \(F\)
3. \(b\notin F\)，且 \(b_1,b_2\) 中一个在 \(F\)、一个不在 \(F\)
4. \(b\notin F,\; b_1,b_2\in F\)

同时自动排除：

- \(b,b_1,b_2\in F\)（即 FFF）
- \(b,b_1,b_2\notin F\)（即 NNN，已由 (S1) 统一覆盖）

---

## 10. Variable Domains

\[
p_s \ge 0,\qquad \forall s\in S
\]

\[
q_b \ge 0,\qquad \forall b\in\mathcal{B}
\]

\[
r_{kb}\ge 0,\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

\[
x_{kb}\in\{0,1\},
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

---

## 11. Compact Full Formulation

\[
\max \;\; \frac{1}{|K|}\sum_{k\in K}\sum_{b\in\mathcal{B}}\big(r_{kb}-c_b x_{kb}\big)
\]

s.t.

### Hybrid price definition

\[
q_b = P_F(b), \qquad \forall b\in F
\]

\[
q_b = p_{|b|}, \qquad \forall b\in\mathcal{B}\setminus F
\]

### Customer choice

\[
\sum_{b\in\mathcal{B}} x_{kb}\le 1, \qquad \forall k\in K
\]

\[
v_k(b)-q_b \ge -M_k(1-x_{kb}),
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

\[
v_k(b)-q_b
\ge
v_k(b')-q_{b'} - M_k(1-x_{kb}),
\qquad
\forall k\in K,\forall b,b'\in\mathcal{B},\; b'\neq b
\]

### Payment linearization

\[
r_{kb}\le q_b,
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

\[
r_{kb}\le \bar q_b x_{kb},
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

\[
r_{kb}\ge q_b-\bar q_b(1-x_{kb}),
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

\[
r_{kb}\ge 0,
\qquad \forall k\in K,\forall b\in\mathcal{B}
\]

### Strong non-\(F\) size-level subadditivity

\[
p_s \le p_{s_1}+p_{s_2},
\qquad
\forall (s_1,s_2,s)\in \mathcal T
\]

### Mixed / fixed-parent hybrid subadditivity

\[
q_b \le q_{b_1}+q_{b_2},
\qquad
\forall b\in\mathcal{B},\;
\forall (b_1,b_2)\in \Pi^\star(b)
\]

满足：

\[
\big( b\in F \;\vee\; b_1\in F \;\vee\; b_2\in F \big)
\]

且

\[
\neg\big( b\in F \wedge b_1\in F \wedge b_2\in F \big)
\]

### Domains

\[
p_s \ge 0,\quad q_b \ge 0,\quad r_{kb}\ge 0,\quad x_{kb}\in\{0,1\}
\]

---

## 12. Interpretation

该 Hybrid Formulation 的逻辑可以概括为：

- 对于 \(F\) 中已知 candidate bundles，价格保持为固定值 \(P_F(b)\)
- 对于不在 \(F\) 中的 bundles，采用统一的 size-based BSP price \(p_s\)
- 最终形成一个 hybrid pricing menu \(q_b\)
- 客户在该 hybrid menu 上进行效用最大化选择
- non-\(F\) 部分内部继续保持强版本的 size-level 次可加
- 所有涉及 \(F\) 的 split relations 再额外补充 hybrid 次可加，以避免与固定 \(P_F\) 拼接后发生 violation
- 对于 \(b,b_1,b_2\in F\) 的纯 candidate 内部次可加，不再重复加入，因为 \(P_F\) 已知满足

---

## 13. Computational Note

如果 \(\mathcal{B}=2^N\setminus\{\varnothing\}\) 为 full bundle space，则：

- \(x_{kb}\) 的变量数量为 \(O(|K|2^n)\)
- customer choice dominance constraints 的数量为 \(O(|K|4^n)\)
- split-related subadditivity constraints 的数量也会非常大

因此在实际求解中，通常会进一步做两类压缩：

1. 用某个实际工作空间 \(G\subseteq 2^N\setminus\{\varnothing\}\) 替代 full bundle space
2. 对 customer choice constraints 和 split constraints 只保留必要或活跃的子集

但从数学建模角度，上述 formulation 是完整且自洽的。