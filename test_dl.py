import asyncio
import sys
from yt_dlp import YoutubeDL
import os

import imageio_ffmpeg
def _get_base_ydl_opts(output_path: str) -> dict:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    opts = {
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        'ffmpeg_location': ffmpeg_exe,
    }
    return opts

async def main():
    url = sys.argv[1]
    
    file_id = "test_123"
    output_dir = 'temp_downloads'
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, f"{file_id}.%(ext)s")

    opts = _get_base_ydl_opts(outtmpl)
    opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
    opts['merge_output_format'] = 'mp4'
    
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Print what we care about
        print("requested_downloads:", [f.get('filepath') for f in info.get('requested_downloads', [])])
        print("filepath:", info.get('filepath'))
        print("_filename:", info.get('_filename'))
        
        # also print dir structure
        import glob
        print("\nFiles in directory:")
        print(glob.glob("temp_downloads/*"))

if __name__ == "__main__":
    asyncio.run(main())
