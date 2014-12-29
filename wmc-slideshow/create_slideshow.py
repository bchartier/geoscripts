# -*- coding: UTF-8 -*-

"""
"""

# package for siplifying shell commands
import scriptine

# packakes for files and directories paths manipulation
import os
import os.path

# csv file access
import csv

# json file access
import json

# package used to download web resources (web map contexts and images through WMS requests)
import urllib2
import urlparse
from urllib import urlencode
import io

# package used to read XML docs
import xml.etree.ElementTree as ET

# package used for image file creation
from PIL import Image

# Mpackage used to print python data structures
from pprint import pprint

# Packages used for logging messages
import logging
import sys


el_wmc_namespace = "{http://www.opengis.net/context}"


class Logger(object):
  """Small class to manage logging messages to a log file and to the stdout
  """

  def __init__ (self):
    """
    """
    self.logger = logging.getLogger('create_slideshow')
    self.logger.setLevel(logging.INFO)
    self.logger.addHandler(logging.FileHandler('create_slideshow.log'))
    self.logger.addHandler(logging.StreamHandler(sys.stdout))

  def log(self, lvl, msg, *args, **kwargs):
    """
    Log a message
    """

    self.logger.log(lvl, msg, *args, **kwargs)

logger = Logger()


def create_images_command(paramfile, nbmaximages=None):
  """Create images for a set of web map contexts (wmc docs) referenced in a csv file.
  The csv file referenced in the paramfile must have a column containing URLs
  for displaying a web map context in geOrchestra mapfishapp. These URLs are not
  permalinks of the contexts themselves!

  :param paramfile: json file containing the parameters of the process
  :param nbmaximages: number of images produced. Can be used to test the process on a limiter number of contexts
  """
  nb_processed_wmc = 0

  # Params
  with open(paramfile) as f:
    params_string = "".join(f.readlines())
    params = json.loads(params_string)

  image_width = params["output"]["image_width"]
  image_height = params["output"]["image_height"]
  image_format = params["output"]["image_format"]
  image_file_ext = params["output"]["image_file_ext"]
  output_dir = params["output"]["output_dir_name"]
  images_dir = params["output"]["images_dir_name"]
  contexts_dir = params["output"]["contexts_dir_name"]
  input_csv_file = params["csv_file"]
  wmc_url_column = params["csv_wmc_url_column"]

  # Paths
  root_dir = params["project_dir"]
  input_csv_file_path =  os.path.realpath(input_csv_file)
  output_dir_path =  os.path.realpath(os.path.join(root_dir, output_dir))
  images_dir_path =  os.path.realpath(os.path.join(output_dir_path, images_dir))
  contexts_dir_path =  os.path.realpath(os.path.join(output_dir_path, contexts_dir))
  logger.log(logging.INFO, u"Chemin du fichier csv : %s", input_csv_file_path)
  logger.log(logging.INFO, u"Chemin du répertoire des images en sortie : %s", images_dir_path)

  # Open csv file
  with open(input_csv_file_path, 'rb') as csv_file:
    csv_reader = csv.DictReader(csv_file, delimiter='\t', quoting=csv.QUOTE_NONE)
    for row in csv_reader:
      permalink = row[wmc_url_column]

      if permalink in (None, "", "None"): continue

      # Build the url of the context to download
      permalink = permalink.replace("%2F", "/")
      context_name = permalink.split("/")[-1]
      wmc_url = "http://www.geopicardie.fr/mapfishapp/ws/wmc/" + context_name
      wmc_path = os.path.realpath(os.path.join(contexts_dir_path, context_name))
      logger.log(logging.INFO, u"Permalien de consultation du contexte : %s", permalink)
      logger.log(logging.DEBUG, u"URL du contexte : %s", wmc_url)
      logger.log(logging.DEBUG, u"Chemin de la copie locale du contexte : %s", wmc_path)

      # if context_name.find("4108") == -1: continue

      # Download the context if it has not been downloaded yet
      if not os.path.isfile(wmc_path):
        http_req = urllib2.Request(wmc_url)
        http_file = urllib2.urlopen(http_req)
        with open(wmc_path, 'wb') as f:
          f.write(http_file.read())

      if not os.path.isfile(wmc_path): continue

      # Build the path of the image to be downloaded
      image_name = os.path.basename(context_name) + image_file_ext
      image_path = os.path.realpath(os.path.join(images_dir_path, image_name))

      # Create the image
      create_image_from_context_path(
        wmc_path, image_path, image_width, image_height, image_format)

      # Number of contexts processed
      nb_processed_wmc += 1
      if nbmaximages is not None and int(nbmaximages) > 0 and nb_processed_wmc >= int(nbmaximages):
        break


def create_image_from_context_path(wmc_path, image_path, image_width, image_height, image_format):
  """
  """

  # Extract wms requests info from the context
  wms_params = extract_wms_params_from_context(wmc_path)
  if wms_params is None: return

  wms_params["width"] = image_width
  wms_params["height"] = image_height
  wms_params["format"] = image_format

  # Download the image
  logger.log(logging.DEBUG, u"Chemin de l'image locale produite : %s", image_path)
  download_image(wms_params, image_path)


def extract_wms_params_from_context(wmc_path):
  """
  """

  root = ET.parse(wmc_path)

  wms_params = {}
  wms_params["layers"] = []


  # srs and image center
  try:
    bbox_xpath = './{0}{1}/{0}{2}'.format(el_wmc_namespace, 'General', 'BoundingBox')
    bbox = root.findall(bbox_xpath)[0]
    center_x = (float(bbox.attrib["minx"])+float(bbox.attrib["maxx"]))/2.
    center_y = (float(bbox.attrib["miny"])+float(bbox.attrib["maxy"]))/2.
    srs = bbox.attrib["SRS"]
    wms_params["crs"] = srs
    wms_params["center_x"] = center_x
    wms_params["center_y"] = center_y
  except Exception as e:
    print("Système de coordonnées ou centre de l'image non trouvé !")
    print(e)
    return


  # image resolution
  try:
    window_xpath = './{0}{1}/{0}{2}'.format(el_wmc_namespace, 'General', 'Window')
    window = root.findall(window_xpath)[0]
    w_width = float(window.attrib["width"])
    w_height = float(window.attrib["height"])
    bbox_width = abs(float(bbox.attrib["maxx"])-float(bbox.attrib["minx"]))
    bbox_height = abs(float(bbox.attrib["maxy"])-float(bbox.attrib["miny"]))
    res_x = w_width/bbox_width
    res_y = w_height/bbox_height
    wms_params["res"] = (res_x + res_y)/2.
    wms_params["bbox_width"] = bbox_width
    wms_params["bbox_height"] = bbox_height
  except Exception as e:
    print("Informations sur les dimensions du contexte manquantes ou mal structurées !")
    print(e)
    return


  # visible layers
  layers_xpath = './{0}{1}/{0}{2}[@hidden="0"]'.format(el_wmc_namespace, 'LayerList', 'Layer')
  layers = root.findall(layers_xpath)
  for layer in layers:
    wms_layer_params = {}
    try:
      service_url_xpath = './{0}{1}[@service="OGC:WMS"]/{0}{2}'.format(
        el_wmc_namespace, 'Server', 'OnlineResource')
      service = layer.find(service_url_xpath)
      wms_layer_params["service"] = service.attrib['{http://www.w3.org/1999/xlink}href']

    except Exception as e:
      print("Informations sur le service WMS manquantes ou mal structurées !")
      print(e)

    try:
      layer_name_xpath = './{0}{1}'.format(el_wmc_namespace, 'Name')
      layer_name = layer.find(layer_name_xpath)
      wms_layer_params["layer_name"] = layer_name.text

    except Exception as e:
      print("Informations sur le service WMS manquantes ou mal structurées !")
      print(e)


    try:
      layer_opacity_xpath = './{0}{1}/{2}{3}'.format(
        el_wmc_namespace, 'Extension', '{http://openlayers.org/context}', 'opacity')
      layer_opacity = layer.find(layer_opacity_xpath)
      wms_layer_params["layer_opacity"] = float(layer_opacity.text)

    except Exception as e:
      wms_layer_params["layer_opacity"] = 1.0


    wms_params["layers"].append(wms_layer_params)


  # pprint(wms_params)
  return wms_params


def download_image(wms_params, image_path):
  """
  """

  center_x = wms_params["center_x"]
  center_y = wms_params["center_y"]
  res = wms_params["res"]

  image_width = wms_params["width"]
  image_height = wms_params["height"]
  bbox_width = wms_params["bbox_width"]
  bbox_height = wms_params["bbox_height"]
  if bbox_width/bbox_height > image_width/image_height:
    bbox_height = bbox_width/image_width*image_height
  else:
    bbox_width = bbox_height/image_height*image_width

  ymin = center_y - bbox_height/2.
  ymax = center_y + bbox_height/2.
  xmin = center_x - bbox_width/2.
  xmax = center_x + bbox_width/2.

  # Create a white image
  transparent_image = Image.new("RGBA", (image_width, image_height), "white")
  transparent_image.putalpha(0)
  full_image = Image.new("RGBA", (image_width, image_height), "white")

  # Loop on layers
  for layer in wms_params["layers"]:

    layer_opacity = layer["layer_opacity"]
    wms_req_url = layer["service"]
    wms_req_parts = urlparse.urlparse(wms_req_url)

    # The keys of the parameters are lowercased
    args = dict((k.lower(), v) for k, v in urlparse.parse_qs(wms_req_parts.query).iteritems())

    args['service'] = 'WMS'
    args['version'] = '1.3.0'
    args['request'] = 'GetMap'
    args['layers'] = layer["layer_name"]
    args['format'] = wms_params["format"]
    args['transparent'] = 'true'
    args['crs'] = wms_params["crs"]
    args['bbox'] = '{0},{1},{2},{3}'.format(xmin, ymin, xmax, ymax)
    args['width'] = wms_params["width"]
    args['height'] = wms_params["height"]

    query = urlencode(args, doseq=True)
    wms_req_parts = urlparse.ParseResult(wms_req_parts.scheme, wms_req_parts.netloc,
                                        wms_req_parts.path, wms_req_parts.params,
                                        query, wms_req_parts.fragment)
    wms_req_url = urlparse.urlunparse(wms_req_parts)

    f = urllib2.urlopen(wms_req_url)
    layer_image_file = io.BytesIO(f.read())
    layer_image = Image.open(layer_image_file)
    if layer_image.mode != "RGBA":
      layer_image = layer_image.convert("RGBA")
    if layer_opacity != 1.0:
      layer_image = Image.blend(layer_image, transparent_image, 1-layer_opacity)

    full_image = Image.alpha_composite(full_image, layer_image)

  # Save image
  full_image.save(image_path)

if __name__ == '__main__':
  scriptine.run()