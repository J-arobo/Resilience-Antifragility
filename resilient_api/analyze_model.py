# Scirpt for diagnosing for  visualizing the model behaviour
#Bar Chart showing which features most influence the model predictions
from learning import train_model, plot_feature_importance
from feature_extraction import extract_features_from_csv

# Load and scale features
X, y = extract_features_from_csv(scale="standard")

# Train model
model = train_model()

# Plot feature importance
plot_feature_importance(model, X.columns)


"""
python analyze_model.py

"""