import base64
import os

def generate_cookie_base64():
    cookie_file = "cookies.txt"
    if not os.path.exists(cookie_file):
        print(f"Error: '{cookie_file}' not found in '{os.getcwd()}'.")
        print("Please export your YouTube cookies as 'cookies.txt' (Netscape format) and place it here.")
        input("Press Enter to exit...")
        return

    try:
        with open(cookie_file, "rb") as f:
            cookie_content = f.read()
            encoded = base64.b64encode(cookie_content).decode("utf-8")
            
        output_file = "cookies_base64.txt"
        with open(output_file, "w") as f:
            f.write(encoded)
            
        print(f"\n✅ Success! The Base64 string has been saved to '{output_file}'.")
        print("Open this file, copy the content, and paste it into Railway Variables as 'YT_COOKIES_BASE64'.")
    except Exception as e:
        print(f"Error processing cookies file: {e}")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    generate_cookie_base64()
