from importlib_metadata import metadata
from CachePath import *
from datetime import datetime
import json
import os
import os.path
from PIL import Image
from PIL.ExifTags import TAGS
from PIL.TiffImagePlugin import IFDRational
import gc
import errno
import traceback

class Album(object):
    def __init__(self, path):
        self._path = trim_base(path)
        self._photos = list()
        self._albums = list()
        self._photos_sorted = True
        self._albums_sorted = True
    @property
    def photos(self):
        return self._photos
    @property
    def albums(self):
        return self._albums
    @property
    def path(self):
        return self._path
    def __str__(self):
        return self.path
    @property
    def cache_path(self):
        return json_cache(self.path)
    @property
    def date(self):
        self._sort()
        if len(self._photos) == 0 and len(self._albums) == 0:
            return datetime(1900, 1, 1)
        elif len(self._photos) == 0:
            return self._albums[-1].date
        elif len(self._albums) == 0:
            return self._photos[-1].date
        return max(self._photos[-1].date, self._albums[-1].date)
    def __cmp__(self, other):
        return cmp(self.date, other.date)
    def add_photo(self, photo):
        self._photos.append(photo)
        self._photos_sorted = False
    def add_album(self, album):
        self._albums.append(album)
        self._albums_sorted = False
    def _sort(self):
        if not self._photos_sorted:
            self._photos.sort(key=lambda item: (item.date, item.name))
            self._photos_sorted = True
        if not self._albums_sorted:
            self._albums.sort(key=lambda item: item.date)
            self._albums_sorted = True
    @property
    def empty(self):
        if len(self._photos) != 0:
            return False
        if len(self._albums) == 0:
            return True
        for album in self._albums:
            if not album.empty:
                return False
        return True
        
    def cache(self, base_dir):
        self._sort()
        fp = open(os.path.join(base_dir, self.cache_path), 'w')
        json.dump(self, fp, cls=PhotoAlbumEncoder)
        fp.close()
    @staticmethod
    def from_cache(path, cache_base=None):
        fp = open(path, "r")
        dictionary = json.load(fp)
        fp.close()
        return Album.from_dict(dictionary, cache_base=cache_base)
    @staticmethod
    def from_dict(dictionary, cripple=True, cache_base=None):
        album = Album(dictionary["path"])
        for photo in dictionary["photos"]:
            photo_obj = Photo.from_dict(photo, untrim_base(album.path), cache_base)
            if photo_obj.valid:
                album.add_photo(photo_obj)
        if not cripple:
            for subalbum in dictionary["albums"]:
                album.add_album(Album.from_dict(subalbum), cripple)
        album._sort()
        return album
    def to_dict(self, cripple=True):
        self._sort()
        subalbums = []
        if cripple:
            for sub in self._albums:
                if not sub.empty:
                    subalbums.append({ "path": trim_base_custom(sub.path, self._path), "date": sub.date })
        else:
            for sub in self._albums:
                if not sub.empty:
                    subalbums.append(sub)
        return { "path": self.path, "date": self.date, "albums": subalbums, "photos": self._photos }
    def photo_from_path(self, path):
        for photo in self._photos:
            if trim_base(path) == photo._path:
                return photo
        return None
    
class Photo(object):
    # Thumbnail details: (size, square?, quality). Largest first, as smaller ones are created from larger.
    thumb_sizes = [ (1024, False, 75), (150, True, 75) ]
    def __init__(self, path, thumb_path=None, attributes=None, album_base=None):
        if album_base:
            set_cache_path_base(album_base)
        self._path = trim_base(path)
        self.is_valid = True
        try:
            mtime = file_mtime(path)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # Probably because the file no longer exists in the album loaded from json
            # traceback.print_exc()
            self.is_valid = False
            return

        if attributes:
            self._attributes = attributes
        else:
            self._attributes = {}
            self._attributes["dateTimeFile"] = mtime

        thumbs_exist = True
        for size in Photo.thumb_sizes:
            if not self.check_thumb_exists(thumb_path, path, size[0], size[1]):
                thumbs_exist = False
                break

        thumbs_needed = True
        if self._attributes is not None and self._attributes["dateTimeFile"] >= mtime and thumbs_exist:
            thumbs_needed = False

        try:
            image = Image.open(path)
        except KeyboardInterrupt:
            raise
        except:
            self.is_valid = False
            return

        # Always regenerate metadata since it also sets self._orientation.
        # (If it is too slow, we could recalculate self._orientation from the orientation metadata.)
        self._metadata(image)

        if thumbs_needed:
            self._thumbnails(image, thumb_path, path)
#           self._thumbnail_lns(thumb_path)
    
    def _metadata(self, image):
        self._attributes["size"] = image.size
        self._orientation = 1
        try:
            info = image._getexif()
        except KeyboardInterrupt:
            raise
        except:
            return
        if not info:
            return
        
        exif = {}
        for tag, value in list(info.items()):
            decoded = TAGS.get(tag, tag)
            if (isinstance(value, tuple) or isinstance(value, list)) and (isinstance(decoded, str) or isinstance(decoded, str)) and decoded.startswith("DateTime") and len(value) >= 1:
                value = value[0]
            if isinstance(value, str) or isinstance(value, str):
                value = value.strip().partition("\x00")[0]
                if (isinstance(decoded, str) or isinstance(decoded, str)) and decoded.startswith("DateTime"):
                    try:
                        value = datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except KeyboardInterrupt:
                        raise
                    except:
                        continue
            exif[decoded] = value
        
        if "Orientation" in exif:
            self._orientation = exif["Orientation"];
            if self._orientation in range(5, 9):
                self._attributes["size"] = (self._attributes["size"][1], self._attributes["size"][0])
            if self._orientation - 1 < len(self._metadata.orientation_list):
                self._attributes["orientation"] = self._metadata.orientation_list[self._orientation - 1]
        if "Make" in exif:
            self._attributes["make"] = exif["Make"]
        if "Model" in exif:
            self._attributes["model"] = exif["Model"]
        if "ApertureValue" in exif:
            self._attributes["aperture"] = exif["ApertureValue"]
        elif "FNumber" in exif:
            self._attributes["aperture"] = exif["FNumber"]
        if "FocalLength" in exif:
            self._attributes["focalLength"] = exif["FocalLength"]
        if "ISOSpeedRatings" in exif:
            self._attributes["iso"] = exif["ISOSpeedRatings"]
        if "ISO" in exif:
            self._attributes["iso"] = exif["ISO"]
        if "PhotographicSensitivity" in exif:
            self._attributes["iso"] = exif["PhotographicSensitivity"]
        if "ExposureTime" in exif:
            self._attributes["exposureTime"] = exif["ExposureTime"]
        if "Flash" in exif and exif["Flash"] in self._metadata.flash_dictionary:
            try:
                self._attributes["flash"] = self._metadata.flash_dictionary[exif["Flash"]]
            except KeyboardInterrupt:
                raise
            except:
                pass
        if "LightSource" in exif and exif["LightSource"] in self._metadata.light_source_dictionary:
            try:
                self._attributes["lightSource"] = self._metadata.light_source_dictionary[exif["LightSource"]]
            except KeyboardInterrupt:
                raise
            except:
                pass
        if "ExposureProgram" in exif and exif["ExposureProgram"] < len(self._metadata.exposure_list):
            self._attributes["exposureProgram"] = self._metadata.exposure_list[exif["ExposureProgram"]]
        if "SpectralSensitivity" in exif:
            self._attributes["spectralSensitivity"] = exif["SpectralSensitivity"]
        if "MeteringMode" in exif and exif["MeteringMode"] < len(self._metadata.metering_list):
            self._attributes["meteringMode"] = self._metadata.metering_list[exif["MeteringMode"]]
        if "SensingMethod" in exif and exif["SensingMethod"] < len(self._metadata.sensing_method_list):
            self._attributes["sensingMethod"] = self._metadata.sensing_method_list[exif["SensingMethod"]]
        if "SceneCaptureType" in exif and exif["SceneCaptureType"] < len(self._metadata.scene_capture_type_list):
            self._attributes["sceneCaptureType"] = self._metadata.scene_capture_type_list[exif["SceneCaptureType"]]
        if "SubjectDistanceRange" in exif and exif["SubjectDistanceRange"] < len(self._metadata.subject_distance_range_list):
            self._attributes["subjectDistanceRange"] = self._metadata.subject_distance_range_list[exif["SubjectDistanceRange"]]
        if "ExposureCompensation" in exif:
            self._attributes["exposureCompensation"] = exif["ExposureCompensation"]
        if "ExposureBiasValue" in exif:
            self._attributes["exposureCompensation"] = exif["ExposureBiasValue"]
        if "DateTimeOriginal" in exif:
            self._attributes["dateTimeOriginal"] = exif["DateTimeOriginal"]
        if "DateTime" in exif:
            self._attributes["dateTime"] = exif["DateTime"]
    
    _metadata.flash_dictionary = {0x0: "No Flash", 0x1: "Fired",0x5: "Fired, Return not detected",0x7: "Fired, Return detected",0x8: "On, Did not fire",0x9: "On, Fired",0xd: "On, Return not detected",0xf: "On, Return detected",0x10: "Off, Did not fire",0x14: "Off, Did not fire, Return not detected",0x18: "Auto, Did not fire",0x19: "Auto, Fired",0x1d: "Auto, Fired, Return not detected",0x1f: "Auto, Fired, Return detected",0x20: "No flash function",0x30: "Off, No flash function",0x41: "Fired, Red-eye reduction",0x45: "Fired, Red-eye reduction, Return not detected",0x47: "Fired, Red-eye reduction, Return detected",0x49: "On, Red-eye reduction",0x4d: "On, Red-eye reduction, Return not detected",0x4f: "On, Red-eye reduction, Return detected",0x50: "Off, Red-eye reduction",0x58: "Auto, Did not fire, Red-eye reduction",0x59: "Auto, Fired, Red-eye reduction",0x5d: "Auto, Fired, Red-eye reduction, Return not detected",0x5f: "Auto, Fired, Red-eye reduction, Return detected"}
    _metadata.light_source_dictionary = {0: "Unknown", 1: "Daylight", 2: "Fluorescent", 3: "Tungsten (incandescent light)", 4: "Flash", 9: "Fine weather", 10: "Cloudy weather", 11: "Shade", 12: "Daylight fluorescent (D 5700 - 7100K)", 13: "Day white fluorescent (N 4600 - 5400K)", 14: "Cool white fluorescent (W 3900 - 4500K)", 15: "White fluorescent (WW 3200 - 3700K)", 17: "Standard light A", 18: "Standard light B", 19: "Standard light C", 20: "D55", 21: "D65", 22: "D75", 23: "D50", 24: "ISO studio tungsten"}
    _metadata.metering_list = ["Unknown", "Average", "Center-weighted average", "Spot", "Multi-spot", "Multi-segment", "Partial"]
    _metadata.exposure_list = ["Not Defined", "Manual", "Program AE", "Aperture-priority AE", "Shutter speed priority AE", "Creative (Slow speed)", "Action (High speed)", "Portrait", "Landscape", "Bulb"]
    _metadata.orientation_list = ["Horizontal (normal)", "Mirror horizontal", "Rotate 180", "Mirror vertical", "Mirror horizontal and rotate 270 CW", "Rotate 90 CW", "Mirror horizontal and rotate 90 CW", "Rotate 270 CW"]
    _metadata.sensing_method_list = ["Not defined", "One-chip color area sensor", "Two-chip color area sensor", "Three-chip color area sensor", "Color sequential area sensor", "Trilinear sensor", "Color sequential linear sensor"]
    _metadata.scene_capture_type_list = ["Standard", "Landscape", "Portrait", "Night scene"]
    _metadata.subject_distance_range_list = ["Unknown", "Macro", "Close view", "Distant view"]

    def check_thumb_exists(self, thumb_path, original_path, size, square=False):
        thumb_path = os.path.join(thumb_path, image_cache(self._path, size, square, False))
        info_string = "%s -> %spx" % (os.path.basename(original_path), str(size))
        if square:
            info_string += ", square"
        # Thumb is deemed to exist (and be up-to-date) if its file exists and is later than the photo's timestamp
        if os.path.exists(thumb_path) and self._attributes and file_mtime(thumb_path) >= self._attributes["dateTimeFile"]:
            return True
        return False
        
    def _thumbnail(self, image, thumb_path, original_path, size, quality, square=False, suffix=None):
        thumb_path = os.path.join(thumb_path, image_cache(self._path, size, square, False, suffix))
        info_string = "%s -> %spx" % (os.path.basename(original_path), str(size))
        if square:
            info_string += ", square"
        message("thumbing", info_string)
        gc.collect()
        try:
            image = image.copy()
        except KeyboardInterrupt:
            raise
        except:
            try:
                image = image.copy() # we try again to work around PIL bug
            except KeyboardInterrupt:
                raise
            except:
                message("corrupt image", os.path.basename(original_path))
                return
        if square:
            if image.size[0] > image.size[1]:
                left = (image.size[0] - image.size[1]) / 2
                top = 0
                right = image.size[0] - ((image.size[0] - image.size[1]) / 2)
                bottom = image.size[1]
            else:
                left = 0
                top = (image.size[1] - image.size[0]) / 2
                right = image.size[0]
                bottom = image.size[1] - ((image.size[1] - image.size[0]) / 2)
            image = image.crop((left, top, right, bottom))
            gc.collect()
        image.thumbnail((size, size), Image.ANTIALIAS)
        try:
            tomake = os.path.dirname(thumb_path)
            os.makedirs(tomake)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                pass
            else:
                message('folder failure', os.path.basename(thumb_path))
                return
        try:
            image.save(thumb_path, "JPEG", quality=quality)
            # Return the thumbnail'ed image, so it can be reused to create the next one
            return image
        except KeyboardInterrupt:
            try:
                os.unlink(thumb_path)
            except:
                pass
            raise
        except:
            traceback.print_exc()
            message("save failure", os.path.basename(thumb_path))
            try:
                os.unlink(thumb_path)
            except:
                return

    def _thumbnails(self, image, thumb_path, original_path):
        mirror = image
        if self._orientation == 2:
            # Vertical Mirror
            mirror = image.transpose(Image.FLIP_LEFT_RIGHT)
        elif self._orientation == 3:
            # Rotation 180
            mirror = image.transpose(Image.ROTATE_180)
        elif self._orientation == 4:
            # Horizontal Mirror
            mirror = image.transpose(Image.FLIP_TOP_BOTTOM)
        elif self._orientation == 5:
            # Horizontal Mirror + Rotation 270
            mirror = image.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.ROTATE_270)
        elif self._orientation == 6:
            # Rotation 270
            mirror = image.transpose(Image.ROTATE_270)
        elif self._orientation == 7:
            # Vertical Mirror + Rotation 270
            mirror = image.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270)
        elif self._orientation == 8:
            # Rotation 90
            mirror = image.transpose(Image.ROTATE_90)
        for size in Photo.thumb_sizes:
            thumb = self._thumbnail(mirror, thumb_path, original_path, size[0], size[2], square=size[1], suffix=None)
            # Return generated thumbnail so it can be used to generate further ones, which is faster than creating each from the original
            if thumb:
                mirror = thumb
    @property
    def name(self):
        return os.path.basename(self._path)
    @property
    def valid(self):
        return self.is_valid
    def __str__(self):
        return self.name
    @property
    def path(self):
        return self._path
    @property
    def image_caches(self):
        return [image_cache(self._path, size[0], size[1], False) for size in Photo.thumb_sizes]
    @property
    def date(self):
        correct_date = None;
        if not self.is_valid:
            correct_date = datetime(1900, 1, 1)
        if "dateTimeOriginal" in self._attributes:
            correct_date = self._attributes["dateTimeOriginal"]
        elif "dateTime" in self._attributes:
            correct_date = self._attributes["dateTime"]
        else:
            correct_date = self._attributes["dateTimeFile"]
        return correct_date

    def __cmp__(self, other):
        date_compare = cmp(self.date, other.date)
        if date_compare == 0:
            return cmp(self.name, other.name)
        return date_compare
    @property
    def attributes(self):
        return self._attributes
    @staticmethod
    def from_dict(dictionary, basepath, cache_base=None):
        del dictionary["date"]
        path = os.path.join(basepath, dictionary["name"])
        del dictionary["name"]
        for key, value in dictionary.items():
            if key.startswith("dateTime"):
                try:
                    dictionary[key] = datetime.strptime(dictionary[key], "%a %b %d %H:%M:%S %Y")
                except KeyboardInterrupt:
                    raise
                except:
                    pass
        return Photo(path, cache_base, dictionary)
    def to_dict(self):
        photo = { "name": self.name, "date": self.date }
        photo.update(self.attributes)
        return photo

    def _thumbnail_lns(self, cache_path):
        for sizes in Photo.thumb_sizes:
            size = sizes[0]
            square = sizes[1]
            thumb_path = os.path.join(cache_path, image_cache(self._path, size, square, False))
            thumb_path_dump = os.path.join(cache_path, image_cache(self._path, size, square))
            info_string = "%s -> %spx" % (os.path.basename(self._path), str(size))
            if square:
                info_string += ", square"
            if thumb_path_dump == thumb_path or (os.path.exists(thumb_path) and not os.path.exists(thumb_path_dump)):
                continue
            elif os.path.exists(thumb_path) and os.path.exists(thumb_path_dump):
                message("duplicate", info_string)
                try:
                    os.unlink(thumb_path_dump)
                except KeyboardInterrupt:
                    message('unlink failure', os.path.basename(thumb_path))
                    raise
                continue
            else:
                message("linking", info_string)
            try:
                tomake = os.path.dirname(thumb_path)
                os.makedirs(tomake)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    pass
                else:
                    message('folder failure', os.path.basename(thumb_path))
                    return
            try:
                os.rename(thumb_path_dump, thumb_path)
            except KeyboardInterrupt:
                try:
                    os.unlink(thumb_path)
                except:
                    pass
                raise
            except:
                message("link failure", os.path.basename(thumb_path))
                try:
                    os.unlink(thumb_path)
                except:
                    pass

class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%a %b %d %H:%M:%S %Y")
        if isinstance(obj, Album) or isinstance(obj, Photo):
            return obj.to_dict()
        if isinstance(obj, IFDRational):
            return [obj.numerator, obj.denominator]
        return json.JSONEncoder.default(self, obj)
        
