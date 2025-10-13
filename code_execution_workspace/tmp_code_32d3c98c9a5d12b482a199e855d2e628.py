# -*- coding: utf-8 -*-
def factorial_recursive(n):
    """Calculate the factorial of a non-negative integer n using recursion."""
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers.")
    if n == 0 or n == 1:
        return 1
    return n * factorial_recursive(n - 1)


# Example usage:
print(factorial_recursive(5))  # Output: 120
