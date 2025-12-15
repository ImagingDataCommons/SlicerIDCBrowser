import sys
import urllib.parse
import requests
import webbrowser

def resolve_url(url):
    # Parse the URL
    parsed_url = urllib.parse.urlparse(url)

    # Remove the scheme (idcbrowser://) from the URL and split the path
    path_parts = parsed_url.netloc.split('/') + parsed_url.path.split('/')[1:]

    # Check the first part of the path to determine the endpoint
    if path_parts[0] == 'collections':
        new_url = "http://localhost:2042/idc/collections"
       # Open the new URL in a web browser
        webbrowser.open(new_url)
    elif path_parts[0] == 'series':
        new_url = f"http://localhost:2042/idc/download/seriesInstanceUID/{path_parts[1]}"
    elif path_parts[0] == 'studies':
        new_url = f"http://localhost:2042/idc/download/studyInstanceUID/{path_parts[1]}"
    else:
        print(f"Unhandled path: {path_parts[0]}")
        return

    # Make the request to the new URL
    response = requests.get(new_url)

    # Print the response
    print(response.text)

if __name__ == "__main__":
    # The URL is passed as the first argument
    url = sys.argv[1]

    # Resolve the URL
    resolve_url(url)
