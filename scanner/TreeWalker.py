import os
import os.path
import sys
from datetime import datetime
from PhotoAlbum import Photo, Album, PhotoAlbumEncoder
from CachePath import *
import json
import traceback
#from multiprocessing.pool import ThreadPool

class TreeWalker:
    def __init__(self, album_path, cache_path):
        try:
            self.album_path = os.path.abspath(album_path)
            self.cache_path = os.path.abspath(cache_path)
            set_cache_path_base(self.album_path)
            self.all_albums = list()
            self.all_photos = list()
            #self.pool = ThreadPool(10)
            message("will start walking", "")
            self.walk(self.album_path)
            self.big_lists()
            self.remove_stale()
            message("complete", "")
        except Exception as e:
            import traceback
            print(f" error {str(e)}")
            traceback.print_exc()
    def walk(self, path):
        next_level()
        if not os.access(path, os.R_OK | os.X_OK):
            message("access denied", os.path.basename(path))
            back_level()
            return None
        message("walking", os.path.basename(path))
        cache = os.path.join(self.cache_path, json_cache(path))
        cached = False
        cached_album = None
        if os.path.exists(cache):
            try:
                cached_album = Album.from_cache(cache, self.cache_path)
                if file_mtime(path) <= file_mtime(cache):
                    message("full cache", os.path.basename(path))
                    cached = True
                    album = cached_album
                    #self.pool.map(lambda x: x._thumbnail_lns(self.cache_path), album.photos)
                    #self.pool.wait_completion()
                    for photo in album.photos:
                        self.all_photos.append(photo)
                else:
                    message("partial cache", os.path.basename(path))
            except KeyboardInterrupt:
                raise
            except :
                message("corrupt cache", os.path.basename(path))
                traceback.print_exc()
                cached_album = None
        if not cached:
            album = Album(path)
        for entry in os.listdir(path):
            if entry[0] == '.':
                continue
            try:
                entry = entry
            except KeyboardInterrupt:
                raise
            except:
                next_level()
                message("unicode error", entry.decode(sys.getfilesystemencoding(), "replace"))
                back_level()
                continue
            entry = os.path.join(path, entry)
            if os.path.isdir(entry):
                next_walked_album = self.walk(entry)
                if next_walked_album is not None:
                    album.add_album(next_walked_album)
            elif not cached and os.path.isfile(entry):
                next_level()
                cache_hit = False
                if cached_album:
                    cached_photo = cached_album.photo_from_path(entry)
                    if cached_photo and file_mtime(entry) <= cached_photo.attributes["dateTimeFile"]:
                        message("cache hit", os.path.basename(entry))
#                        cached_photo._thumbnail_lns(self.cache_path)
                        cache_hit = True
                        photo = cached_photo
                if not cache_hit:
                    message("metainfo", os.path.basename(entry))
                    photo = Photo(entry, self.cache_path)
                if photo.is_valid:
                    self.all_photos.append(photo)
                    album.add_photo(photo)
                else:
                    message("unreadable", os.path.basename(entry))
                back_level()
        if not album.empty:
            message("caching", os.path.basename(path))
            album.cache(self.cache_path)
            self.all_albums.append(album)
        else:
            message("empty", os.path.basename(path))
        back_level()
        return album
    def big_lists(self):
        photo_list = []
        self.all_photos.sort(key=lambda item: (item.date, item.name))
        for photo in self.all_photos:
            photo_list.append(photo.path)
        message("caching", "all photos path list")
        fp = open(os.path.join(self.cache_path, "all_photos.json"), 'w')
        json.dump(photo_list, fp, cls=PhotoAlbumEncoder)
        fp.close()
    def remove_stale(self):
        message("cleanup", "building cache list")
        all_cache_entries = { "all_photos.json": True, "latest_photos.json": True }
        for album in self.all_albums:
            all_cache_entries[album.cache_path] = True
        for photo in self.all_photos:
            for entry in photo.image_caches:
                all_cache_entries[entry] = True
        # Make each an absolute path
        all_cache_entries = {os.path.join(self.cache_path, cache_item): True for cache_item in all_cache_entries}
        # Start the stale walk
        self.remove_stale_walk(self.cache_path, all_cache_entries)
    def remove_stale_walk(self, cache_path, all_cache_entries):
        message("remove_stale_walk", cache_path)
        files_found = 0
        next_level()
        for cache_file in os.listdir(cache_path):
            try:
                cache_file = cache_file.decode(sys.getfilesystemencoding())
            except KeyboardInterrupt:
                raise
            except:
                pass
            fullpath = os.path.join(cache_path, cache_file)
            if os.path.isdir(fullpath):
                sub_files_found = self.remove_stale_walk(fullpath, all_cache_entries)
                # If no files were found in the subdirectory, remove it
                if sub_files_found == 0:
                    message("remove_stale_walk", "Removing stale dir " + fullpath)
                    os.rmdir(fullpath)
                files_found += sub_files_found
            elif os.path.isfile(fullpath):
                if fullpath not in all_cache_entries:
                    message("remove_stale_walk", "Removing stale file " + fullpath)
                    os.unlink(fullpath)
                else:
                    files_found += 1
        back_level()
        return files_found
