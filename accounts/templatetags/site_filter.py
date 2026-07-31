from django import template
from django.conf import settings

register = template.Library()

@register.filter(is_safe=True)
def domain(value):
    value = settings.DOMAIN
    return value

@register.filter(is_safe=True)
def sitename(value):
    value = settings.SITE_NAME
    return value