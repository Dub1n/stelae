# AGENTS.md

## Command Tool

!IMPORTANT: Only **USE BASH COMMANDS** unless asked otherwise or no bash command is available for the task.

*Bash Shell is available to commands invoked as `["bash","-lc",…]`*

## Placeholders

- NEVER write mocks or placeholders unless explicitly asked to.

## DRY

- Avoid duplicating code. Extract common logic into reusable functions, components, or modules.
- **Specifics:**
  - Identify duplicated code patterns.
  - Create reusable functions or components for common tasks.
  - Use higher-order functions or components to abstract common logic.
  - Ensure that changes to shared code are thoroughly tested to avoid breaking existing functionality.

## Test-Driven Development (TDD)

Follow TDD practices where applicable.

- This applies to:
  - new features
  - infrastructure

- This doesn't apply to:
  - small changes
  - small test harnesses
  - code that would not meaningfully benefit from having a test written for it
  - code that can be tested comprehensively with few commands

- Write tests *before* writing the code. This forces you to think about the interface and behavior first.
- **Specifics:**
  - Write unit tests for individual functions and classes, focusing on isolated behavior.
  - Use integration tests to verify interactions between different modules and components.
  - Aim for high test coverage (80%+) to ensure that most of the code is tested.
  - Use mocking and stubbing to isolate units under test and control dependencies.

If existing code does that not have appropriate tests (unit tests, end-to-end tests, etc.) is encounetered, the following approach is employed:

1. Complete current task
2. After summarising the work completed, notify the user of the missing tests and affected components
3. If tests are to be written, the user will notify you. If they do not, proceed with the next task
4. If the user requests "present test plan" (or words to that effect), present a plan for the user to provide in a new chat:
  The user will provide a test plan to the agent
  The agent will write a test *without* reading the components that are to be tested, but is told in the test plan what the required inputs/outputs/endpoints etc are, just not the actual implementation of the components
  The agent will write the tests for the components such that they pass when the requirements are met and fail should they not, ensuring coverage of edge cases and likely points of failure
  The agent will run the tests on the components and, should either the tests or the components need fixing, conduct the fixes required

## SOLID Design Principles - Coding Assistant Guidelines

When generating, reviewing, or modifying code, follow these guidelines to ensure adherence to SOLID principles:

### 1. Single Responsibility Principle (SRP)

- Never allow a file to exceed 500 lines.
- If a file approaches 400 lines, break it up immediately. - Treat 1000 lines as unacceptable, even temporarily.
- Use folders and naming conventions to keep small files logically grouped.
- Each class must have only one reason to change.
- Limit class scope to a single functional area or abstraction level.
- Keep functions under 30-40 lines.
- When a class exceeds 100-150 lines, consider if it has multiple responsibilities.
- Separate cross-cutting concerns (logging, validation, error handling) from business logic.
- Create dedicated classes for distinct operations like data access, business rules, and UI.
- Method names should clearly indicate their singular purpose.
- If a method description requires "and" or "or", it likely violates SRP.
- Prioritize composition over inheritance when combining behaviors.

### 2. Open/Closed Principle (OCP)

- Design classes to be extended without modification.
- Use abstract classes and interfaces to define stable contracts.
- Implement extension points for anticipated variations.
- Favor strategy patterns over conditional logic.
- Use configuration and dependency injection to support behavior changes.
- Avoid switch/if-else chains based on type checking.
- Provide hooks for customization in frameworks and libraries.
- Design with polymorphism as the primary mechanism for extending functionality.

### 3. Liskov Substitution Principle (LSP)

- Ensure derived classes are fully substitutable for their base classes.
- Maintain all invariants of the base class in derived classes.
- Never throw exceptions from methods that don't specify them in base classes.
- Don't strengthen preconditions in subclasses.
- Don't weaken postconditions in subclasses.
- Never override methods with implementations that do nothing or throw exceptions.
- Avoid type checking or downcasting, which may indicate LSP violations.
- Prefer composition over inheritance when complete substitutability can't be achieved.

### 4. Interface Segregation Principle (ISP)

- Create focused, minimal interfaces with cohesive methods.
- Split large interfaces into smaller, more specific ones.
- Design interfaces around client needs, not implementation convenience.
- Avoid "fat" interfaces that force clients to depend on methods they don't use.
- Use role interfaces that represent behaviors rather than object types.
- Implement multiple small interfaces rather than a single general-purpose one.
- Consider interface composition to build up complex behaviors.
- Remove any methods from interfaces that are only used by a subset of implementing classes.

### 5. Dependency Inversion Principle (DIP)

- High-level modules should depend on abstractions, not details.
- Make all dependencies explicit, ideally through constructor parameters.
- Use dependency injection to provide implementations.
- Program to interfaces, not concrete classes.
- Place abstractions in a separate package/namespace from implementations.
- Avoid direct instantiation of service classes with 'new' in business logic.
- Create abstraction boundaries at architectural layer transitions.
- Define interfaces owned by the client, not the implementation.

### Implementation Guidelines

- When starting a new class, explicitly identify its single responsibility.
- Document extension points and expected subclassing behavior.
- Every file, class, and function should do one thing only.
- If a file, class, or function has multiple responsibilities, split it immediately.
- Each view, manager, or utility should be laser-focused on one concern.
- Write interface contracts with clear expectations and invariants.
- Question any class that depends on many concrete implementations.
- Every functionality should be in a dedicated class, struct, or protocol, even if it’s small.
- Favor composition over inheritance, but always use object-oriented thinking.
- Code must be built for reuse, not just to “make it work.”
- Use factories, dependency injection, or service locators to manage dependencies.
- Review inheritance hierarchies to ensure LSP compliance.
- Regularly refactor toward SOLID, especially when extending functionality.
- Use design patterns (Strategy, Decorator, Factory, Observer, etc.) to facilitate SOLID adherence.
- All class, method, and variable names must be descriptive and intention-revealing.
- Avoid vague names like data, info, helper, or temp.
- Always code as if someone else will scale this.
- Include extension points (e.g., protocol conformance, dependency injection) from day one.

### Warning Signs

- God classes that do "everything"
- Methods with boolean parameters that radically change behavior
- Deep inheritance hierarchies
- Classes that need to know about implementation details of their dependencies
- Circular dependencies between modules
- High coupling between unrelated components
- Classes that grow rapidly in size with new features
- Methods with many parameters

## Mdular Design

- Code should connect like Lego
— interchangeable, testable, and isolated.
- Ask: “Can I reuse this class in a different screen or project?” If not, refactor it.
- Reduce tight coupling between components. Favor dependency injection or protocols.

## Manager and Coordinator Patterns

- Use ViewModel, Manager, and Coordinator naming conventions for logic separation:
- UI logic ➝ ViewModel - Business logic ➝ Manager - Navigation/state flow ➝ Coordinator
- Never mix views and business logic directly.

## Project settings and data

ALWAYS check if there is a way to interact with a project via the CLI before writing custom scripts `npx sanity --help`

## TypeScript

### Content modelling

- Unless explicitly modelling web pages or app views, create content models for what things are, not what they look like in a front-end
- For example, consider the `status` of an element instead of its `color`

### Basic schema types

- ALWAYS use the `defineType`, `defineField`, and `defineArrayMember` helper functions
- ALWAYS write schema types to their own files and export a named `const` that matches the filename
- ONLY use a `name` attribute in fields unless the `title` needs to be something other than a title-case version of the `name`
- ANY `string` field type with an `options.list` array with fewer than 5 options must use `options.layout: "radio"`
- ANY `image` field must include `options.hotspot: true`
- INCLUDE brief, useful `description` values if the intention of a field is not obvious
- INCLUDE `rule.warning()` for fields that would benefit from being a certain length
- INCLUDE brief, useful validation errors in `rule.required().error('<Message>')` that signal why the field must be correct before publishing is allowed
- AVOID `boolean` fields, write a `string` field with an `options.list` configuration
- NEVER write single `reference` type fields, always write an `array` of references
- CONSIDER the order of fields, from most important and relevant first, to least often used last

### Dependency Injection

Favor dependency injection using interfaces to promote loose coupling and testability. Use a registry or container to manage dependencies.

## Autonomy

If task completion presents immediate follow-ups, complete them without without notifying the user. Examples incude (but aren't limited to): running tests, verifying implemented code quality, updating documentation, necessary updates in related files.

## Communication

- Eliminate: emojis, filler, hype, conversational transitions.
- Prioritize: directive phrasing; aim at cognitive rebuilding, not tone-matching.
- Disable: engagement/sentiment-boosting behaviors.
- Suppress: metrics like satisfaction scores and continuation bias.
- Goal: improve the user's independent, high-fidelity thinking.

## Teaching

The user is learning software development through building projects with Agents such as yourself. When appropriate, provide information on the method of implemtation with detail at the level of the task (high-level explanation for broad tasks, low-level for specific tasks).
If the user asks a question or requests a task that suggests they do not understand an aspect of the code, infrastructure, or any other part of the code, provide an educational snippet to help them understand the systems at play and the specifics of why and how you completed the task requirements as you would/did.

## Troubleshooting

### File Editing

If you are struggling to edit a file (3+ attempts to make one edit) due to parsing, syntax, or other command issues, write the new contents of the file (or the diff if longer than 100 lines) to the chat and ask the user to update the file's contents.
