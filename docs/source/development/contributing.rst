Contributing
============

We welcome contributions to MassGen! This guide will help you get started.

Getting Started
---------------

1. Fork the repository
2. Clone your fork
3. Create a new branch
4. Make your changes
5. Submit a pull request

Development Setup
-----------------

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install in development mode
   pip install -e .
   pip install -e .[dev]

Coding Standards
----------------

* Follow PEP 8
* Use type hints
* Write docstrings
* Add unit tests
* Update documentation

Testing
-------

.. code-block:: bash

   # Run tests
   pytest

   # With coverage
   pytest --cov=massgen

   # Run specific tests
   pytest tests/test_agents.py

Pull Request Process
--------------------

1. Update documentation
2. Add tests for new features
3. Ensure all tests pass
4. Update CHANGELOG.md
5. Submit PR with clear description