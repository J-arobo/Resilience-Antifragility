from stable_baselines3 import PPO
from app import ResilienceEnv  # import the class from app.py

env = ResilienceEnv()
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=5000)

# Save the trained agent
model.save("resilience_agent")