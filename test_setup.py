"""
Quick test script to verify the setup
"""

import os
import sys

def test_imports():
    """Test if all required packages can be imported"""
    print("Testing imports...")
    
    try:
        import gradio
        print("✓ gradio")
    except ImportError as e:
        print(f"✗ gradio: {e}")
        return False
    
    try:
        import playwright
        print("✓ playwright")
    except ImportError as e:
        print(f"✗ playwright: {e}")
        return False
    
    try:
        import google.generativeai
        print("✓ google-generativeai")
    except ImportError as e:
        print(f"✗ google-generativeai: {e}")
        return False
    
    try:
        import pandas
        print("✓ pandas")
    except ImportError as e:
        print(f"✗ pandas: {e}")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✓ python-dotenv")
    except ImportError as e:
        print(f"✗ python-dotenv: {e}")
        return False
    
    return True


def test_files():
    """Test if all required files exist"""
    print("\nTesting files...")
    
    required_files = [
        'app.py',
        'yayy.py',
        'page_navigator.py',
        'Dockerfile',
        'requirements.txt',
        'README.md'
    ]
    
    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - MISSING")
            all_exist = False
    
    return all_exist


def test_api_key():
    """Test if API key is available"""
    print("\nTesting API key...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key and api_key != 'your_api_key_here':
        print("✓ GEMINI_API_KEY is set")
        return True
    else:
        print("⚠ GEMINI_API_KEY not set (will need to be provided in UI)")
        return True  # Not a failure, just a warning


def main():
    """Run all tests"""
    print("="*60)
    print("CONFIGURATOR EXTRACTOR - SETUP TEST")
    print("="*60 + "\n")
    
    results = []
    
    # Test imports
    results.append(("Imports", test_imports()))
    
    # Test files
    results.append(("Files", test_files()))
    
    # Test API key
    results.append(("API Key", test_api_key()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    
    if all_passed:
        print("✓ All tests passed! Ready to deploy.")
        print("\nNext steps:")
        print("1. Review DEPLOYMENT.md for deployment instructions")
        print("2. Test locally: python app.py")
        print("3. Build Docker: docker build -t configurator-extractor .")
        print("4. Deploy to Hugging Face Spaces")
    else:
        print("✗ Some tests failed. Please fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
