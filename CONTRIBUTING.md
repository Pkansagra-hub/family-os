# Contributing to Family AI Cognitive Architecture

Contracts-first. See `contracts/` and `contracts/POLICY_VERSIONING.md`.


Thank you for your interest in contributing to the Family AI Cognitive Architecture project! We welcome contributions from the community and are excited to collaborate with you.

## 🤝 Code of Conduct

This project adheres to the [Code of Conduct](CODE_OF_CONDUCT.md) that we expect all contributors to follow. Please be respectful, inclusive, and constructive in all interactions.

## � Licensing

FamilyOS is proprietary, patent-pending software. By contributing, you agree that your submissions fall under the FamilyOS Proprietary License and that rights in those contributions are assigned to the project as described in [LICENSE](LICENSE).

## �🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Basic understanding of cognitive architecture concepts
- Familiarity with async Python programming

### Development Environment Setup

1. **Fork the repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/your-username/family-ai-cognitive-architecture.git
   cd family-ai-cognitive-architecture
   ```

2. **Set up development environment**
   ```bash
   # Create virtual environment
   python -m venv .venv

   # Activate virtual environment
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate

   # Install dependencies including dev tools
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

## 📋 Types of Contributions

We welcome various types of contributions:

### 🐛 Bug Reports
- Use GitHub Issues with the "bug" label
- Include reproduction steps, expected vs actual behavior
- Provide system information and error logs

### ✨ Feature Requests
- Use GitHub Issues with the "enhancement" label
- Clearly describe the feature and its benefits
- Consider how it fits with the cognitive architecture

### 🔧 Code Contributions
- Bug fixes
- New features
- Performance improvements
- Documentation improvements
- Test coverage improvements

### 📚 Documentation
- API documentation
- Tutorials and guides
- Architecture explanations
- Code comments and docstrings

## 💻 Development Workflow

### 1. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b bugfix/issue-number-description
```

### 2. Make Your Changes
- Follow the existing code style and patterns
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass

### 3. Code Quality Checks
```bash
# Format code
black .

# Type checking
mypy .

# Linting
flake8 .

# Run tests
pytest

# Test coverage
pytest --cov=family_ai --cov-report=html
```

### 4. Commit Your Changes
```bash
# Use conventional commit format
git commit -m "feat: add new memory consolidation algorithm"
git commit -m "fix: resolve race condition in sync manager"
git commit -m "docs: update API documentation for retrieval service"
```

#### Commit Message Format
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### 5. Push and Create Pull Request
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear title and description
- Reference to any related issues
- Screenshots or demos if applicable

## 🏗️ Architecture Guidelines

### Core Principles

1. **Modularity**: Each module should have a single, well-defined responsibility
2. **Async-First**: Use async/await patterns for I/O operations
3. **Type Safety**: Use type hints and maintain mypy compatibility
4. **Event-Driven**: Leverage the event bus for loose coupling
5. **Privacy-Aware**: Consider privacy implications in all designs

### Code Organization

- **Separation of Concerns**: Keep business logic separate from I/O and infrastructure
- **Pipeline Pattern**: Use the P01-P20 pipeline architecture
- **Service Layer**: Wrap complex operations in service classes
- **Policy Enforcement**: Apply policies consistently across all operations

### Testing Guidelines

- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test interactions between components
- **Pipeline Tests**: Test end-to-end pipeline operations
- **Performance Tests**: Ensure scalability requirements are met

```python
# Example test structure
def test_memory_writer_basic_ingestion():
    """Test basic memory ingestion through writer."""
    # Arrange
    writer = MemoryWriter()
    content = {"text": "test content", "metadata": {}}

    # Act
    result = await writer.write(content)

    # Assert
    assert result.success
    assert result.memory_id is not None
```

### Documentation Standards

- **Docstrings**: Use Google-style docstrings
- **Type Hints**: Provide comprehensive type annotations
- **API Documentation**: Document all public APIs
- **Architecture Decisions**: Document significant design choices

```python
def process_memory_item(
    item: MemoryItem,
    policy: PolicyConfig
) -> ProcessingResult:
    """Process a memory item through the ingestion pipeline.

    Args:
        item: The memory item to process
        policy: Policy configuration for processing

    Returns:
        Processing result with success status and metadata

    Raises:
        PolicyViolationError: If item violates policy constraints
        ProcessingError: If processing fails unexpectedly
    """
```

## 🔍 Review Process

### Pull Request Reviews

All contributions go through a review process:

1. **Automated Checks**: CI/CD pipeline runs tests and quality checks
2. **Code Review**: Maintainers review code for quality and architecture fit
3. **Testing**: Reviewers may test functionality locally
4. **Documentation**: Ensure adequate documentation is provided

### Review Criteria

- **Functionality**: Does it work as intended?
- **Code Quality**: Is it readable, maintainable, and efficient?
- **Tests**: Are there adequate tests with good coverage?
- **Documentation**: Is it properly documented?
- **Architecture**: Does it fit with the overall system design?
- **Security**: Are there any security implications?
- **Privacy**: Does it respect family privacy principles?

## 🏷️ Issue Labels

We use the following labels to categorize issues:

- `bug`: Something isn't working
- `enhancement`: New feature or request
- `documentation`: Improvements or additions to documentation
- `good first issue`: Good for newcomers
- `help wanted`: Extra attention is needed
- `priority-high`: High priority items
- `pipeline-*`: Issues related to specific pipelines (P01-P20)
- `component-*`: Issues related to specific components

## 📞 Getting Help

- **Support Guide**: Start with [SUPPORT.md](SUPPORT.md) for contact options and response expectations
- **GitHub Discussions**: For questions and general discussion
- **GitHub Issues**: For bug reports and feature requests
- **Documentation**: Check the docs/ directory for detailed guides
- **Developer Index**: See `develpoer_index.md` for module details

## 🎯 Development Priorities

Current focus areas for contributions:

1. **Core Memory Operations** (P01-P02 pipelines)
2. **Security and Privacy** (E2EE, policy enforcement)
3. **Performance Optimization** (embeddings, retrieval)
4. **Testing Coverage** (unit and integration tests)
5. **Documentation** (API docs, tutorials)

## 🙏 Recognition

Contributors will be recognized in:

- GitHub contributors list
- Release notes for significant contributions
- Project documentation
- Community acknowledgments

Thank you for contributing to Family AI Cognitive Architecture!
