import os
import glob
import requests
import shutil
import re
from requests.auth import HTTPBasicAuth


def sanitize_filename(text):
    """Sanitize the credit string to be filesystem-safe."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:100]  # limit length


def credit_images(folder_path, rename=False):
    """
    Receives a folder containing .png image files and uses a reverse image lookup
    service (e.g., TinEye API) to determine who to credit for each image.

    Args:
        folder_path (str): Path to the folder containing .png files.
        rename (bool): If True, rename images to include credit in the filename.

    Returns:
        dict: A mapping from image filename to credit information 
              (e.g., source URL or creator name).
    """
    api_url = os.getenv('TINEYE_API_URL', 'https://api.tineye.com/rest/search/')
    api_public = os.getenv('TINEYE_API_PUBLIC')
    api_private = os.getenv('TINEYE_API_PRIVATE')

    if not api_public or not api_private:
        raise RuntimeError("TinEye API credentials not found in environment variables.")

    credits = {}
    for filepath in glob.glob(os.path.join(folder_path, '*.png')):
        filename = os.path.basename(filepath)
        with open(filepath, 'rb') as img_file:
            files = {
                'image_upload': img_file
            }
            try:
                response = requests.post(
                    api_url,
                    files=files,
                    auth=HTTPBasicAuth(api_public, api_private)
                )
                response.raise_for_status()
            except requests.RequestException as e:
                credits[filename] = f"API error: {e}"
                continue

        try:
            data = response.json()
            matches = data.get('results', {}).get('matches', [])
            if matches:
                best = matches[0]
                backlink = best.get('backlinks', [None])[0]  # TinEye uses 'backlinks' list
                credit_info = backlink or 'Credit found, but no backlink URL provided.'
            else:
                credit_info = 'No matches found.'
        except Exception as e:
            credit_info = f"Failed to parse API response: {e}"

        credits[filename] = credit_info

        if rename and 'http' in credit_info:
            credit_name = sanitize_filename(credit_info.split('/')[2])  # domain name
            base, ext = os.path.splitext(filepath)
            new_name = f"{base}_{credit_name}{ext}"
            new_path = os.path.join(folder_path, os.path.basename(new_name))
            shutil.move(filepath, new_path)

    return credits
