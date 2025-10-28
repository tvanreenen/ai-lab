#!/usr/bin/env python3
"""
FastMCP Hello World Server with Ngrok Tunnel

A simple MCP server that demonstrates:
- Resource: Static greeting content
- Tool: Dynamic greeting function
- Prompt: Reusable greeting template

Exposed via ngrok for external testing.
"""

import asyncio
import json
from typing import Any, Dict, List
from fastmcp import FastMCP
from pyngrok import ngrok
import signal
import sys


# Initialize FastMCP server
mcp = FastMCP("Hello World Server")


@mcp.resource("greeting://hello")
async def get_greeting() -> str:
    """A simple greeting resource that returns static content."""
    return "Hello, World! Welcome to the FastMCP Hello World Server!"


@mcp.tool()
async def greet_user(name: str) -> str:
    """
    Greet a user with their name.
    
    Args:
        name: The name of the user to greet
        
    Returns:
        A personalized greeting message
    """
    return f"Hello, {name}! Nice to meet you! 👋"


@mcp.prompt("hello_prompt")
async def hello_prompt_template() -> str:
    """
    A reusable prompt template for greeting interactions.
    
    Returns:
        A prompt template for greeting conversations
    """
    return """You are a friendly assistant that helps users with greetings and introductions.

When a user asks for a greeting:
1. Be warm and welcoming
2. Ask about their name if not provided
3. Offer to help with introductions or small talk
4. Keep responses concise but friendly

Example responses:
- "Hello! I'd love to help you get started. What's your name?"
- "Hi there! How can I make your day a little brighter?"
- "Welcome! I'm here to help with any questions you might have."
"""


def main():
    """Main server function that starts the MCP server and ngrok tunnel."""
    print("🚀 Starting FastMCP Hello World Server...")
    
    tunnel = None
    public_url = None
    
    # Try to create ngrok tunnel first
    try:
        # Create HTTP tunnel
        tunnel = ngrok.connect(8000, "http")
        public_url = tunnel.public_url
        
        print(f"🌐 Public ngrok URL: {public_url}")
        print(f"✅ MCP Server will run locally at: http://localhost:8000")
        print("\n📋 Available endpoints:")
        print(f"   Resource: {public_url}/resource/greeting://hello")
        print(f"   Tool: {public_url}/tool/greet_user")
        print(f"   Prompt: {public_url}/prompt/hello_prompt")
        
        print("\n🧪 Test the server:")
        print(f"   curl {public_url}/resource/greeting://hello")
        print(f"   curl -X POST {public_url}/tool/greet_user -H 'Content-Type: application/json' -d '{{\"name\": \"Alice\"}}'")
        print(f"   curl {public_url}/prompt/hello_prompt")
        
    except Exception as e:
        print(f"⚠️  Could not create ngrok tunnel: {e}")
        print("💡 To use ngrok:")
        print("   1. Sign up at: https://dashboard.ngrok.com/signup")
        print("   2. Get your authtoken: https://dashboard.ngrok.com/get-started/your-authtoken")
        print("   3. Run: ngrok config add-authtoken YOUR_TOKEN")
        print("\n🔄 Running server locally only...")
        print(f"✅ MCP Server will run locally at: http://localhost:8000")
        print("\n📋 Available endpoints:")
        print(f"   Resource: http://localhost:8000/resource/greeting://hello")
        print(f"   Tool: http://localhost:8000/tool/greet_user")
        print(f"   Prompt: http://localhost:8000/prompt/hello_prompt")
        
        print("\n🧪 Test the server:")
        print(f"   curl http://localhost:8000/resource/greeting://hello")
        print(f"   curl -X POST http://localhost:8000/tool/greet_user -H 'Content-Type: application/json' -d '{{\"name\": \"Alice\"}}'")
        print(f"   curl http://localhost:8000/prompt/hello_prompt")
    
    print("\n⏹️  Press Ctrl+C to stop the server")
    
    try:
        # Start the FastMCP server (this blocks)
        mcp.run(transport="http", host="127.0.0.1", port=8000)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        # Cleanup ngrok if it was created
        if tunnel:
            try:
                ngrok.disconnect(tunnel.public_url)
                ngrok.kill()
            except:
                pass


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n🛑 Received interrupt signal, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the server
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Server error: {e}")
