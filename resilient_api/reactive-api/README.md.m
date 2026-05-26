Reactive API 

- It improves upron the Naive version by introducing basic error handling and fallback logic. 
- The service should gracefully handle bad input and minor disruptions without crushing.

What makes it Reactive:
IT has the following featuree.
1. input validation - Checks for missing or invalid data
2. Graceful errror handling - Returns meaningful error messages
3. Fallback logic (optioal) Could return default values or cached results
HTTP status codes - Uses 400 for client erros, 500 for server errors.