# 📚 Research

These documents were written on **October 2, 2026, before any code existed**. They capture the reasoning behind ProPass: what real cashierless systems do, which datasets and models were considered, and the original build plan. Any numbers in them are *proposed* budgets, not measured results. The measured results are in [training.md](../training.md).

| Doc | What's inside | Read it when… |
|---|---|---|
| 📘 [technical-report.md](technical-report.md) | The full synthesis: recommendation, architecture alternatives, tracking and event design, roadmap, demo script, resume bullets, interview talking points | You want the whole story, or you're preparing to present the project |
| 🏪 [commercial-identity.md](commercial-identity.md) | How commercial checkout-free systems work, camera choices, identity and QR or passkey session design | You're working on authentication or multi-camera |
| 🗃️ [datasets.md](datasets.md) | A 24-source catalog of retail and product datasets with licenses, plus a self-recording plan | You're adding real-camera data |
| 🧠 [models-training.md](models-training.md) | Detector, classifier and tracker options, training strategy, and an open-source code review | You're swapping or upgrading models |

> [!NOTE]
> The report plans a real phone camera and eight products. The MVP that got built swapped those for a **Unity simulation** and five products, so labeled data and rare cases could be generated quickly. The architecture (merchandise detector, SKU classifier, physical-object ledger, reversible events) carried over unchanged.
