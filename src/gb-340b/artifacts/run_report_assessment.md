# Run report assessment (LLM)

- generated_at_utc: `2026-03-26T23:27:14.846654+00:00`

This run looks **meaningfully useful for prioritizing human review**, but **not strong enough to treat as an automated decision tool**. In plain terms: the model appears able to move more likely eligibility-confirmation findings toward the top of the queue, which can help a CE team spend limited review time more efficiently. At the same time, it still misses many true findings and its probability scores should be treated as **directional risk signals**, not as definitive answers.

A good way to anchor the results is the underlying event rate in the test set. The **test positive rate is 29.3%**, which means roughly 3 out of 10 claims in the historical test sample ended up being positive for the target outcome. If we reviewed claims at random, we would expect about that same hit rate on average. The model’s job is to do better than random by concentrating more of those likely findings near the top.

The strongest headline metric here is **precision at the top 10% = 55.7%**. That means if the team reviewed only the highest-ranked 10% of claims, about **56 out of 100** would be expected to be true findings in the backtest. Random review at that same volume would have produced about **29 out of 100**. Said another way, the reported **lift of about 1.9x** means the top-ranked claims are nearly **twice as productive as random selection**. For a business user, that is a practical signal that the ranking is doing useful work.

The tradeoff is **recall at the top 10% = 18.9%**. Recall tells us how much of all true findings we capture at a given review budget. Here, reviewing the top 10% would catch only about **19% of all positives** in the test slice. So this is **not** a “catch most issues” setting; it is a **“find better leads first”** setting. That distinction matters. The model appears better suited to helping a team prioritize scarce audit capacity than to serve as a broad safety net.

The budget metrics make that tradeoff easier to understand in operational terms:

- **Top 1%:** precision **66.7%**, recall **2.3%**, lift **2.27x**  
  Very concentrated, but tiny coverage. Best if review capacity is extremely limited and the goal is to work only the most promising claims.
- **Top 5%:** precision **56.2%**, recall **9.6%**, lift **1.92x**  
  A strong “tight queue” option. Reviewers get a materially better hit rate than random, but still touch only a small share of total findings.
- **Top 10%:** precision **55.7%**, recall **19.0%**, lift **1.90x**  
  Similar efficiency to top 5%, with meaningfully more findings captured overall. This often looks like a reasonable starting point for a prioritized worklist.
- **Top 20%:** precision **48.8%**, recall **33.2%**, lift **1.66x**  
  Efficiency drops, but one-third of positives are now reached. This may fit teams that can absorb more volume and are willing to trade some reviewer productivity for broader coverage.
- **Top 30%:** precision **44.3%**, recall **45.2%**, lift **1.51x**  
  Almost half of all positives are captured, but the queue is much less concentrated. Still better than random, just less sharply prioritized.

In practical business terms, these budget points suggest the model has **real value as a prioritization layer**, especially when review capacity is constrained. The biggest decision is not “is the model perfect?” but rather **where the team wants to sit on the efficiency-versus-coverage curve**:

- If the team wants the **highest reviewer yield**, stay near the top 5–10%.
- If the team wants to **surface more total findings**, move toward 20–30% and accept lower hit rate.
- If the team expects the model to **catch most problematic claims**, this run does not support that expectation.

The broader ranking metrics are more moderate. **ROC AUC = 0.652** and **PR AUC = 0.446** indicate the model has **some discriminatory power**, meaning it can separate higher-risk from lower-risk claims better than chance, but it is far from a highly separative model. For non-technical readers:

- **ROC AUC** is a general “sorting quality” measure. A value of **0.5** would be random; **0.652** means the model is better than random, but not exceptionally strong.
- **PR AUC** is often more useful when we care about finding positives efficiently. Here, **0.446** is consistent with a model that has useful prioritization ability, but still leaves substantial room for improvement.

These numbers are important because they reinforce the same business interpretation: **helpful for queue ordering, not reliable enough to replace human review or downstream validation**.

The probability-quality metrics also matter, but they should be interpreted carefully. **Brier score = 0.1939** and **log loss = 0.5740** are measures of how well the predicted probabilities line up with reality. Lower is better for both, but there is no universal pass/fail cutoff that a business user should memorize. The right takeaway is simpler:

- These metrics suggest the model’s probabilities are **usable as relative signals**.
- They do **not** by themselves prove that a score like 0.60 means a literal 60% real-world chance in a tightly calibrated sense.
- So teams should use the probabilities primarily for **ranking and banding** (for example, high/medium/low review priority), rather than assuming exact probability precision.

That interpretation fits the latest scoring output well. In the current scored population of **1,205 claims**:

- **121** are labeled **high**
- **241** are **medium**
- **843** are **low**

The score range is relatively compressed: from **0.1401** to **0.6907**, with a mean of **0.2762**. A compressed range usually means the model is not finding extremely obvious “sure thing” claims versus extremely obvious “safe” claims. Instead, it is making more modest distinctions across claims. That is another sign to avoid over-reading the raw percentages. The scores are likely more useful as **priority ordering** than as absolute truth estimates.

A few additional observations help frame confidence and limitations:

- The model was trained on **12,867 training snapshots** and tested on **2,103 rows**, which is enough to learn patterns, but not so large that we should assume the results are fully stable across all clients, pharmacies, drugs, and time periods.
- There were **50,000 claims** in upstream stages, but only **13,018 audit outcomes** and **1,205 currently scored claims**. That reduction is normal in many workflows, but it means the model is learning from and being applied to a narrower subset than the total raw claims universe.
- **Best iteration = 72** suggests training stopped at a point that balanced fit and overfitting reasonably well, but it does not change the core business interpretation.
- The latest claim month is **2024-06-30**. As with any historical backtest, actual future performance can drift if claim mix, CE behavior, pharmacy patterns, audit practices, or data quality change.

For CE client-facing business users, the safest plain-language summary is:

- The model appears to be **doing a credible job of pushing more likely findings to the top**.
- The gain is **material**: top-ranked claims are about **1.9x as productive as random** at the 10% review level.
- The model is **not broad-coverage enough** to rely on if the goal is to catch most findings with a small review budget.
- The scores should support **human triage and workflow prioritization**, not final determinations.

If this were being positioned with clients, a reasonable message would be that the model can help answer: **“Which claims should we look at first?”** It is much less suited to answering: **“Which claims are definitively in or out?”**

A practical way to use this run would be to start with a **tiered review strategy**:

- **High priority:** first queue for immediate human review
- **Medium priority:** secondary queue when capacity allows or when specific accounts need broader coverage
- **Low priority:** generally defer, sample, or monitor rather than routinely review all

Because no explicit capacity target was provided, there is no single recommended cut point. Still, based on these results, the **top 5–10%** looks like the most attractive zone if the goal is reviewer efficiency, while **20–30%** is more appropriate if the business wants broader finding capture and can tolerate lower yield.

The main caution is to avoid overclaiming. This run supports **prioritization value**, but not certainty. Some high-scored claims will still be false positives, and many real findings will remain outside the top-ranked group. That is normal for this kind of model. The right success standard is whether it helps the team deploy human review effort more effectively than they could with simple rules or random selection.

Overall, this is a **solid but not elite prioritization run**. It looks strong enough to be operationally useful in a human-in-the-loop workflow, especially for focused review queues, while still warranting careful monitoring, periodic recalibration, and clear messaging that it is an assistive ranking tool rather than a compliance decision engine.
