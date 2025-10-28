#!/usr/bin/env python3
"""
Test client for the FastMCP Hello World Server via ngrok
"""

import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_ngrok_server():
    """Test the FastMCP server via ngrok."""
    server_url = "https://musicologically-subaggregative-librada.ngrok-free.dev/mcp"
    
    print("🧪 Testing FastMCP Hello World Server via ngrok...")
    print(f"📡 Connecting to: {server_url}")
    
    try:
        async with Client(transport=StreamableHttpTransport(server_url)) as client:
            # Test ping
            print("\n1️⃣ Testing ping...")
            ping_result = await client.ping()
            print(f"   ✅ Ping successful: {ping_result}")
            
            # List tools
            print("\n2️⃣ Listing tools...")
            tools = await client.list_tools()
            print(f"   📋 Available tools: {[tool.name for tool in tools]}")
            
            # Test greet_user tool
            print("\n3️⃣ Testing greet_user tool...")
            greeting = await client.call_tool("greet_user", {"name": "Alice"})
            print(f"   👋 Greeting result: {greeting.content[0].text}")
            
            # List resources
            print("\n4️⃣ Listing resources...")
            resources = await client.list_resources()
            print(f"   📚 Available resources: {[res.uri for res in resources]}")
            
            # Test greeting resource
            print("\n5️⃣ Testing greeting resource...")
            resource = await client.read_resource("greeting://hello")
            print(f"   📖 Resource content: {resource[0].text}")
            
            # List prompts
            print("\n6️⃣ Listing prompts...")
            prompts = await client.list_prompts()
            print(f"   💬 Available prompts: {[prompt.name for prompt in prompts]}")
            
            # Test hello_prompt
            print("\n7️⃣ Testing hello_prompt...")
            prompt = await client.get_prompt("hello_prompt", {})
            print(f"   📝 Prompt content: {prompt.messages[0].content.text[:100]}...")
            
            print("\n🎉 All tests passed! Server is working correctly via ngrok.")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    return True


async def test_local_server():
    """Test the FastMCP server locally."""
    server_url = "http://localhost:8000/mcp"
    
    print("🧪 Testing FastMCP Hello World Server locally...")
    print(f"📡 Connecting to: {server_url}")
    
    try:
        async with Client(transport=StreamableHttpTransport(server_url)) as client:
            # Test ping
            print("\n1️⃣ Testing ping...")
            ping_result = await client.ping()
            print(f"   ✅ Ping successful: {ping_result}")
            
            # Test greet_user tool
            print("\n2️⃣ Testing greet_user tool...")
            greeting = await client.call_tool("greet_user", {"name": "Local User"})
            print(f"   👋 Greeting result: {greeting.content[0].text}")
            
            print("\n🎉 Local server test passed!")
            
    except Exception as e:
        print(f"❌ Local test failed: {e}")
        return False
    
    return True


async def main():
    """Run all tests."""
    print("🚀 FastMCP Hello World Server Test Suite")
    print("=" * 50)
    
    # Test ngrok server
    ngrok_success = await test_ngrok_server()
    
    print("\n" + "=" * 50)
    
    # Test local server
    local_success = await test_local_server()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"   🌐 Ngrok server: {'✅ PASS' if ngrok_success else '❌ FAIL'}")
    print(f"   🏠 Local server: {'✅ PASS' if local_success else '❌ FAIL'}")
    
    if ngrok_success and local_success:
        print("\n🎉 All tests passed! Your FastMCP server is working perfectly!")
        return True
    else:
        print("\n⚠️  Some tests failed. Check the server status.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print("\n✅ Test suite completed successfully!")
    else:
        print("\n❌ Test suite failed!")
        exit(1)