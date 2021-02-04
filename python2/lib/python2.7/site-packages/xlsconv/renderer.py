import pystache
import os


def render(context, template_path):
    # Configure template renderer
    folder, template = os.path.split(template_path)
    template_name, ext = os.path.splitext(template)
    renderer = pystache.Renderer(
        search_dirs=[folder],
        file_extension=ext[1:],
    )
    return renderer.render('{{>%s}}' % template_name, context)
