def factorial_iterative(n):
    """Calculate the factorial of a non-negative integer n using iteration."""
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers.")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

# Example usage:
print(factorial_iterative(5))  # Output: 120