<!--
  Sync Impact Report
  ==================
  Version change: 1.1.0 → 1.2.0 (MINOR — new principle added)
  Modified principles: None renamed/removed
  Added sections:
    - Principle V: Code Styling & Quality (strict type hinting)
    - Architecture Constraints: extended with type hinting enforcement rule
    - Development Workflow: added static analysis gate
  Removed sections: None
  Templates requiring updates:
    - .specify/templates/tasks-template.md ⚠ pending — tests still marked "OPTIONAL" (carried from v1.0.0)
    - .specify/templates/plan-template.md ✅ aligned — Constitution Check placeholder is principle-agnostic
    - .specify/templates/spec-template.md ✅ aligned
  Deferred items: None
-->

# Mafia Project Constitution

## Core Principles

### I. Test-Driven Development (NON-NEGOTIABLE)

All production code MUST be written using the TDD cycle:

- **Write tests FIRST**: Unit and integration tests must be authored before the corresponding implementation.
- **Verify failure**: Tests MUST be confirmed to fail before implementation begins.
- **Red-Green-Refactor**: Implement the minimum code to pass tests (green), then refactor while keeping tests green.
- **No untested code**: Every new feature, bug fix, and refactoring MUST include tests that validate the intended behavior.
- **Test at the right level**: Unit tests for business logic in services; integration tests for API endpoints and external interactions; contract tests for inter-service boundaries.

**Rationale**: TDD ensures code correctness, prevents regressions, and drives better design by forcing the developer to think about the interface before the implementation.

### II. Reusability Over Duplication

Code MUST be reusable and DRY (Don't Repeat Yourself):

- **Extract shared logic**: Common functionality MUST be extracted into utility modules (`utils/`) or helper functions (`helpers/`) rather than duplicated across files.
- **Single source of truth**: Every business rule, validation, and transformation MUST exist in exactly one place.
- **Compose, don't copy**: New features MUST compose existing utilities and services rather than copying and modifying similar code.
- **Util/helper organization**: Utilities MUST be organized by domain or concern (e.g., `utils/validation.py`, `utils/formatting.py`), not by feature.

**Rationale**: Duplication increases maintenance burden, introduces inconsistent behavior, and makes bugs harder to fix. A single change in a utility propagates correctly everywhere it is used.

### III. Separation of Concerns

Architecture MUST enforce clear separation of concerns:

- **Thin controllers/consumers**: Controllers, views, and WebSocket consumers MUST be thin — they handle only request parsing, routing, response formatting, and HTTP/WS protocol concerns. No business logic.
- **Business logic in services**: All business logic, domain rules, orchestration, and data access MUST reside in dedicated service modules.
- **Models are data, not behavior**: Models represent data structure and persistence. Complex behavior belongs in services.
- **Single responsibility**: Each service module MUST have a single, well-defined responsibility. Services with multiple unrelated responsibilities MUST be split.

**Rationale**: Separating concerns makes the codebase testable (services can be unit-tested in isolation), maintainable (changes to business rules don't touch HTTP plumbing), and readable (each file has a clear, single purpose).

### IV. RESTful API Design

All HTTP APIs MUST follow RESTful conventions consistently:

- **Resource-oriented URLs**: Endpoints MUST use plural nouns for collections, not verbs or actions (e.g., `/rooms/` not `/create-room/`, `/rooms/{id}/members/` not `/rooms/{id}/add-member/`). Actions on resources MUST be expressed via HTTP methods:
  - `GET` — retrieve
  - `POST` — create (or trigger actions on collections)
  - `PUT`/`PATCH` — update
  - `DELETE` — remove
- **Consistent status codes**: Responses MUST use semantically correct HTTP status codes (`201` for creation, `204` for no-content deletes, `400` for validation errors, `401`/`403` for auth failures, `404` for missing resources, `409` for conflicts).
- **Consistent error format**: All error responses MUST follow a uniform structure with at minimum an `error` field. Validation errors MUST include field-level detail.
- **Pagination**: All list endpoints MUST support pagination. Large result sets returned without pagination are non-compliant.
- **Versioning**: Breaking API changes MUST be gated behind a new version prefix (e.g., `/api/v2/`). Existing clients MUST NOT be broken by changes to a released API version.
- **Nested resources**: Sub-resources MUST be nested under their parent (e.g., `/rooms/{code}/members/`), not flattened or accessed via query parameters.

**Rationale**: Consistent RESTful conventions make the API predictable for consumers, reduce documentation burden, and enable standard tooling (API clients, generators, validators) to work without custom configuration.

### V. Code Styling & Quality

All code MUST use strict, modern type hinting and follow consistent quality standards:

- **Type hinting is mandatory**: Every function, method, and module-level variable MUST have complete type annotations. This includes:
  - Parameter types and return types for all functions and methods.
  - Generic types parameterized fully (e.g., `list[dict[str, Any]]` not `list`).
  - `None`-aware optionals explicitly annotated as `X | None` (Python 3.10+ union syntax) or `Optional[X]`.
  - `Any` used sparingly and only when the type is genuinely unknowable at the callsite.
- **No `type: ignore` without justification**: Silencing the type checker with `# type: ignore` comments MUST include a brief reason (e.g., `# type: ignore[union-attr] — Django manager is dynamic`).
- **Strict linting**: A project-level linter configuration (e.g., `ruff`, `mypy` strict mode) MUST be enforced. CI MUST fail on type errors and lint violations.
- **Consistent formatting**: An auto-formatter (e.g., `ruff format`) MUST be used project-wide. Manual formatting deviations are not permitted.
- **Modern syntax**: Code MUST use the modern syntax of the target Python version (3.10+): union types (`X | Y`), `ParamSpec`, `TypeAlias`, structural pattern matching where appropriate, and `collections.abc` generics.

**Rationale**: Type hints serve as living documentation, catch entire classes of bugs at static analysis time, and enable IDE autocompletion and refactoring to work reliably. Consistency removes style debates from code review and makes the codebase uniformly readable.

## Architecture Constraints

These constraints derive directly from the Core Principles:

| Principle | Enforcement Rule |
|-----------|-----------------|
| TDD | Pull requests without corresponding tests MUST be rejected. |
| Reusability | Code review MUST flag duplication; shared utilities MUST be proposed as alternatives. |
| Separation of Concerns | Controller/consumer files MUST NOT contain business logic or direct ORM queries beyond simple lookups. |
| RESTful API Design | Endpoints using non-resource URL patterns (verb-based) MUST be rejected. Response format inconsistencies MUST be flagged. |
| Code Styling & Quality | CI MUST fail on type errors, missing annotations, and lint violations. PRs with `# type: ignore` without justification MUST be rejected. |

**Service layer pattern**: All business logic MUST follow this structure:

```text
controller/consumer → service → model/data access
     (thin)          (business logic)   (persistence)
```

Controllers call services. Services call data access. Controllers never bypass services to access data directly.

## Development Workflow

### TDD Cycle (mandatory for all production code)

1. Write failing test(s) for the feature or bug fix.
2. Run tests to confirm failure (red).
3. Implement minimum code to pass tests (green).
4. Refactor implementation and tests while keeping the suite green.
5. Commit once the cycle is complete.

### Static Analysis Gates

Before committing or opening a PR, the following MUST pass:

1. Type checker (`mypy --strict` or equivalent) — zero errors.
2. Linter (`ruff check`) — zero violations.
3. Formatter (`ruff format --check`) — no diffs.

### Code Review Gates

- **Test coverage**: Every PR MUST include tests that fail without the implementation.
- **Service placement**: Reviewers MUST verify business logic is in services, not controllers/consumers.
- **Duplication check**: Reviewers MUST flag duplicated logic and suggest extraction into utils/helpers.
- **REST compliance**: Reviewers MUST verify URL patterns follow resource-oriented conventions, status codes are correct, and error responses use the uniform format.
- **Type completeness**: Reviewers MUST verify all functions have full type annotations and `# type: ignore` comments are justified.
- **Constitution compliance**: Violations of any constitutional principle block merge.

## Governance

This constitution is the authoritative source for all project practices. It supersedes any conflicting conventions, guidelines, or habits.

- **Amendment procedure**: Amendments require a documented rationale, review of impact on existing code, and approval from the project maintainer. The version number is updated according to semantic versioning.
- **Versioning**: MAJOR (backward-incompatible principle changes or removals), MINOR (new principles or material expansions), PATCH (clarifications or wording fixes).
- **Compliance**: All pull requests are verified against constitutional principles during review. Non-compliant code is not merged.
- **Runtime guidance**: See `CLAUDE.md` for session-specific development instructions.

**Version**: 1.2.0 | **Ratified**: 2026-06-22 | **Last Amended**: 2026-06-22
