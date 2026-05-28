from agent.engine import AgentEngine

agent = AgentEngine()

print("Ash is running. Type 'quit' to exit.\n")

while True:
    user_input = input("You: ")
    if user_input.lower() == "quit":
        break
    response = agent.chat(user_input)
    print(f"\nAsh: {response}\n")