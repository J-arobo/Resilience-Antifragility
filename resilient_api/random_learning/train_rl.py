from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env

def main():
    env = make_vec_env("CartPole-v1", n_envs=4)

    model = PPO("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=10000)
    model.save("ppo_cartpole")

    # Test the trained agent
    obs = env.reset()
    for _ in range(1000):
        action, _states = model.predict(obs)
        obs, rewards, dones, info = env.step(action)
        # env.render()  <-- removed, no display in Docker

    print("Training complete. Model saved to ppo_cartpole.zip")

if __name__ == "__main__":
    main()