# Hygienic mypy plugin for Django

This repo contains a proof-of-concept for a mypy plugin that does not require
the Django runtime to be loaded in order to discover the dynamic aspects of the
Django models.

There's multiple problems to overcome with this approach, the main one being we
don't know which models depend on which other models. With Django there's now
way to determine all fields and attributes a model has just by looking at the
definition. For example a `ForeignKey` defined on another model might add a
related manager attribute to the model. Ideally we'd know about these
relationships in the `get_additional_deps` plugin hook, so we can tell mypy
exactly which relationships exist. The current mypy plugin does this by using
the runtime inforation.

To solve that problem this plugin adds all apps listed in `INSTALLED_APPS` as
dependencies of the declared `DJANGO_SETTINGS_MODULE`, and add
`DJANGO_SETTINGS_MODULE` as a depdencency of `django.conf`. This ensures that
_all_ models in the project will be loaded. `django.conf` is a dependency of
`django.db.models.base`, so any change there will invalidate all model files.
So by adding all models as depdencies there, any change to a model will
invaliate all other models. Not ideal, but it ensures that mypy's caching will
stil work and not cause issues.

The next problem is that a Django app doesn't automatically import it's models,
Django does that dynamically during setup. So to solve that we add the `models`
module as a dependency of the app. Another complication here is that we don't
know which modules are apps until we've parsed the settings module, which can
happen _after_ the `get_additional_deps` hook has been called for an app. To
work around this any module that has a `models` submodule will get a
depdendency on that, unless we can rule out that it's a Django app.

Another issue we need to resolve is app labels. By default these are the same
as the module name, but they can be changed by declaring an `AppConfig`
subclass in an `apps.py` file. So we'll also have to parse these and extract
the app labels so we can translate those to full module paths.

So far this plugin is very much a proof-of-concept, but it's also indicating
that it should be possible to resolve most of Django's dynamic model details
without relying on the runtime, with a major caveat being that custom logic
that dynamically declares attributes, fields, etc. will not be supported.

## Alternative approaches

One alternative could be to write a separate model resolver that does it's own
module discovery and parsing using the `ast` module. That should still be
significantly faster than loading the entire runtime, especially for larger
projects. This would still be limited to detecting statically declared models
and attributes, but it would allow us to gather all the metadata up-front and
properly declare dependencies between modules.
