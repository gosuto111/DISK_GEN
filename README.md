# DISK_GEN
These scripts are how I generate my "music disks" I distribute online.  
Script is pre-configured with my email address and it expects MP3 files,  
change at-will for your use case. I am not responsible for you destroying your data.  

This disk generation system is modeled after the collectable music disks found in Phantasy Star Online  
as such, I have things configured a very speciifc way. If you don't like the constraints I have in place,  
or you just feel like changing things, feel free. But it is my vision that it is used as I have it set up.  

![Disk Box Model](/Example.png)  
^ Image as seen ingame ^

 
## Constraints:  
- Combined playtime of album must not be over 1 hour
- Must be MP3s (you must modify yourself for something different)  
- Final album size cannot be over 128 MB (will fail if larger)
 
 
## Usage:
Download `preset.zip` - extract it's own folder  
00: Change Email (Line 57) to your comment of choice  
01: Place MP3s in `IMPORT/`, their filenames must be their track number (01.mp3, 02.mp3, etc).  
02: Run script (hint: `python3 ./make_disk.py --phase A --source ./IMPORT`)  ! THIS WILL DESTROY ALL METADATA  


## Output (example):
```.
├── COMPRESSED
│   ├── DISK_A001.tar.zst

├── DISK
│   ├── A
│   │   ├── 001
│   │   │   ├── 01 - 5f8421afa5e1cfcb4345c2eaec30ba53d1533a6944a44d4f3f74e2a874a91ae5.mp3
│   │   │   ├── 02 - 81aabbe7461c72150199dc3539825e133e44d5cc7b2f36c7f11544aa94a358b7.mp3
│   │   │   ├── 03 - de1df53ccf52feda117d7dcdd6af2cf4fa6ec420d13fadf1d15af8aa4e48048a.mp3
│   │   │   ├── 04 - 9ad7d1f70f91a17260c1c18a8d942a2959bb2620d4156effb422b694826e6d58.mp3
│   │   │   ├── 05 - 64c0e1f1ba3699a8511f11ba95c16feafa05f3412c8241fb2dbda8a54a7c44fc.mp3
│   │   │   ├── 06 - f9d010464e145496bcb177dd23a66266d3499dd6c1fbc76dab5b9796a472b023.mp3
│   │   │   ├── 07 - 89c45a6fa970346feb3e7f6fa31034a789c1b86aaf4c8e1bed1acbe75c67803c.mp3
│   │   │   ├── 08 - c76a5c42769cba809bc7abe8997d10572736419671481146d432bcf1f49fd8df.mp3
│   │   │   ├── 09 - 74357ba226b98ee0b9cad5519120bb87193695a7c6b1c1e25dc7fe28426d9eb8.mp3
│   │   │   ├── 10 - 27db19191566d710c5dad20b25ca249e8e91a98c17ccd2e816dee3b02c8a1f9b.mp3
│   │   │   ├── checksums.md5
│   │   │   ├── checksums.sha256
│   │   │   └── cover.png
```

![Directory as intended](/dir.png)  
