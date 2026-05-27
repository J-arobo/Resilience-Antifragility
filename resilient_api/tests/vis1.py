import pandas as pd
import matplotlib.pyplot as plt

# Create DataFrame manually
data = {
    'API Variant': ['Naive', 'Reactive', 'Resilient'],
    'Avg Response Time (ms)': [10.23, 4.39, 4136.52],
    'Failure Rate (%)': [100.0, 100.0, 28.6]
}
df = pd.DataFrame(data)

# Bar chart for response time
plt.figure(figsize=(8, 5))
plt.bar(df['API Variant'], df['Avg Response Time (ms)'], color='skyblue')
plt.title('Average Response Time by API Variant')
plt.ylabel('Response Time (ms)')
plt.xlabel('API Variant')
plt.tight_layout()
plt.show()

# Bar chart for failure rate
plt.figure(figsize=(8, 5))
plt.bar(df['API Variant'], df['Failure Rate (%)'], color='salmon')
plt.title('Failure Rate by API Variant')
plt.ylabel('Failure Rate (%)')
plt.xlabel('API Variant')
plt.tight_layout()
plt.show()
