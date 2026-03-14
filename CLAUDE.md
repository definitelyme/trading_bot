Always read the docs/README.md for detailed info and project structure and understand how things were implemented and how it currently works.

- When in doubt, ask clarifying questions about project, before proceeding
- After every debugging section, always update the docs/ folder in the related file or create new structure/files as you see fit (if necessary).

## Model Deletion Safety Rule

**Before making ANY change to the following, you MUST read `docs/valid-reasons-to-delete-any-model.md` in full:**
- `user_data/strategies/AICryptoStrategy.py` — any of the `feature_engineering_*()` or `set_freqai_targets()` functions
- `user_data/config.json` or `user_data/config.live.json` — any field inside the `freqai.feature_parameters` block, `freqai.freqaimodel`, or `freqai.identifier`
- `Dockerfile` — if changing the FreqTrade base image version or XGBoost version

After reading the file, you MUST explicitly tell the developer:
1. Whether the proposed change **requires deleting models** (YES / NO / NEEDS TESTING)
2. If YES — what **alternative approach** could avoid deletion (e.g. changing the identifier instead)
3. If no alternative exists — state that clearly so the developer can make an informed decision

**Do not proceed with the change until the developer acknowledges the model impact.**

The developer is not opposed to deleting models if necessary — they simply want to be informed and consider alternatives first.
