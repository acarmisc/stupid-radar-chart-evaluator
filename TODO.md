# Backlog / TODO

## Critical
- [ ] **Security**: The `.env` file should NEVER contain actual API keys. Current `.env.local` contains `sk-cuA-FkuqFlXMDJ7pXfO1VA`. 
  - Remove `.env.local` and ensure `.env` is not tracked
  - User should create `.env` from `.env.example` with their own credentials
  - Rotate the exposed key immediately (security vulnerability if this repo was public or shared)

## High Priority
- [ ] **README enhancements**:
  - Add detailed command examples with actual outputs
  - Expand configuration guide with table of all env vars
  - Add authentication setup step-by-step instructions
  - Add development setup section for contributors
- [ ] **Error handling**: Add try-catch around CLI main execution path
- [ ] **Validation**: Add input validation for file paths and required flags per scope type
- [ ] **Environment validation**: Check for required env vars before execution

## Medium Priority
- [ ] **Testing infrastructure**:
  - Add integration tests (end-to-end against real repos)
  - Add LLM mocking for deterministic testing
  - Add error case tests
  - Improve golden fixture path handling (currently references local paths)
- [ ] **CI/CD**: Set up GitHub Actions for automated testing
- [ ] **Code quality**: Add ruff pre-commit hooks, mypy type checking
- [ ] **Documentation generation**: Create sphinx or similar for API docs
- [ ] **Performance tests**: Add benchmark tests for algorithmic performance

## Low Priority
- [ ] **Configuration file support**: Add TOML/YAML config file support beyond env vars
- [ ] **Feature flags**: Enable gradual rollouts
- [ ] **Plugin architecture**: Make extensibility for custom signals or languages
- [ ] **Monitoring**: Add instrumentation for production usage metrics
