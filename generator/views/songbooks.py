# -*- coding: utf-8 -*-
#    Copyright (C) 2014 The Patacrep Team
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Songbooks views"""

from django.views.generic import ListView, CreateView, DetailView, UpdateView, \
                                 DeleteView
from django.core.urlresolvers import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.utils.translation import ugettext as _
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404, render
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType
from django.template.defaultfilters import slugify


from generator.decorators import LoginRequiredMixin, OwnerOrPublicRequiredMixin, \
                                OwnerRequiredMixin, owner_required
from generator.models import Songbook, ItemsInSongbook, Song, \
                             Task as GeneratorTask, Layout, Artist
from generator.forms import SongbookCreationForm, LayoutForm


class SongbookPublicList(ListView):
    model = Songbook
    context_object_name = "songbooks"
    template_name = "generator/songbook_public_list.html"

    def get_queryset(self):
        return Songbook.objects.filter(is_public=True
                                       ).order_by('title')


class SongbookPrivateList(LoginRequiredMixin, ListView):
    model = Songbook
    context_object_name = "songbooks"
    template_name = "generator/songbook_private_list.html"

    def get_queryset(self):
        songbooks = Songbook.objects.filter(user=self.request.user
                                       ).order_by('title')
        if len(songbooks) == 1 and 'current_songbook' not in self.request.session:
            self.request.session['current_songbook'] = songbooks[0].id
        return songbooks


class NewSongbook(LoginRequiredMixin, CreateView):
    model = Songbook
    template_name = 'generator/new_songbook.html'
    form_class = SongbookCreationForm

    def get_success_url(self):
        return reverse('set_current_songbook') + '?songbook=' + str(self.object.id)

    def form_valid(self, form):
        form.user = self.request.user
        messages.success(self.request, _(u"Le carnet a été créé."))
        return super(NewSongbook, self).form_valid(form)

    def get_initial(self):
        initial = super(NewSongbook, self).get_initial()
        initial["author"] = self.request.user
        return initial


class ShowSongbook(OwnerOrPublicRequiredMixin, DetailView):
    model = Songbook
    template_name = 'generator/show_songbook.html'
    context_object_name = 'songbook'

    def get_queryset(self):
        return Songbook.objects.filter(id=self.kwargs['id'],
                                       slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(ShowSongbook, self).get_context_data(**kwargs)
        items_list = ItemsInSongbook.objects.prefetch_related(
                   'item', 'item_type'
                   ).filter(songbook=self.object)
        context['items_list'] = items_list
        if self.request.user == self.object.user:
            context['can_edit'] = True
        else:
            context['can_edit'] = False
        return context


class UpdateSongbook(OwnerRequiredMixin, UpdateView):
    model = Songbook
    template_name = 'generator/update_songbook.html'
    form_class = SongbookCreationForm

    def get_queryset(self):
        return Songbook.objects.filter(id=self.kwargs['id'],
                                       slug=self.kwargs['slug'])

    def get_success_url(self):
        return reverse('edit_songbook', kwargs=self.kwargs)


    def form_valid(self, form):
        form.user = self.request.user
        messages.success(self.request, _(u"Le carnet a été modifié."))
        # Update songbook slug
        self.kwargs["slug"] = slugify(form.cleaned_data["title"])
        return super(UpdateSongbook, self).form_valid(form)


@login_required
def set_current_songbook(request):
    """Set a songbook for edition with sessions
     """
    if (request.GET['songbook'] != None):
        songbook_id = request.GET['songbook']
        request.session['current_songbook'] = int(songbook_id)
        if 'next' in request.GET:
            return redirect(request.GET['next'])
        return redirect('song_list')
    else:
        messages.error(request, _(u"Ce carnet n'existe pas."))
        return redirect('songbook_list')


def _add_item(item, songbook, rank, current_item_list):
    """Add an item to a songbook.
    Return True if it has been added, false if not.
    """
    if item not in current_item_list:
        item_in_songbook = ItemsInSongbook(item=item,
                                            songbook=songbook,
                                            rank=rank)
        item_in_songbook.save()
        return True
    else:
        return False


def _get_new_rank(songbook_id):
    """Get the last song in the section, and return this rank plus 1."""
    rank = ItemsInSongbook.objects.filter(songbook=songbook_id).count()
    if rank == None:
        return 1
    else:
        return rank + 1


@login_required
def add_songs_to_songbook(request):
    """Add a list of songs to the current songbook.
    """
    next_url = request.POST['next']

    try:
        songbook_id = request.session['current_songbook']
        songbook = Songbook.objects.get(id=songbook_id, user_id=request.user.id)
    except (KeyError, Songbook.DoesNotExist):
        messages.error(request,
                       _(u"Choisissez un carnet pour ajouter ces chants")
                       )
        return redirect(next_url)

    song_list = request.POST.getlist('songs[]')
    song_added = 0

    current_item_list = [item.item for item in
                            ItemsInSongbook.objects.filter(songbook=songbook)]
    rank = _get_new_rank(songbook_id)

    for song_id in song_list:
        try:
            song = Song.objects.get(id=song_id)
            added = _add_item(item=song,
                              songbook=songbook,
                              rank=rank,
                              current_item_list=current_item_list)
            if added:
                rank += 1
                song_added += 1
                current_item_list.append(song)
        except Song.DoesNotExist:  # May be useless
            pass

    artist_list = request.POST.getlist('artists[]')
    for artist_id in artist_list:
        try:
            artist = Artist.objects.get(id=artist_id)
            song_list = artist.songs.all()
            for song in song_list:
                added = _add_item(item=song,
                              songbook=songbook,
                              rank=rank,
                              current_item_list=current_item_list)
                if added:
                    rank += 1
                    song_added += 1
        except Artist.DoesNotExist:
            pass
    if song_added == 0:
        messages.info(request, _(u"Aucun chant ajouté"))
    elif song_added == 1:
        messages.success(request, _(u"1 chants ajouté"))
    else:
        messages.success(request, _(u"%i chants ajoutés" % (song_added) ))

    return redirect(next_url)

@login_required
def remove_song(request):
    """Remove a song from the current songbook"""
    next_url = request.POST['next']

    try:
        songbook_id = request.session['current_songbook']
        songbook = Songbook.objects.get(id=songbook_id, user_id=request.user.id)
    except (KeyError, Songbook.DoesNotExist):
        messages.error(request,
                       _(u"Choisissez un carnet pour supprimer ce chants")
                       )
        return redirect(next_url)
    song_id = request.POST["song_id"]
    type = ContentType.objects.get(app_label="generator", model="song")
    item = ItemsInSongbook.objects.get(songbook=songbook,
                                       item_type=type,
                                       item_id=song_id)
    item.delete()
    songbook.fill_holes()
    messages.success(request, _(u"Chant retiré du carnet"), extra_tags='removal')
    return redirect(next_url)

@owner_required(('id', 'id'))
def move_or_delete_items(request, id, slug):
    """Remove an item or a list of items from the current songbook
    """
    next_url = request.POST['next']
    songbook = Songbook.objects.get(id=id, slug=slug)
    item_list = {}

    for key in request.POST.keys():
        if key.startswith('item_'):
            item_list[key] = request.POST[key]

    for item_key in item_list.keys():
        item_id = int(item_key[5:])
        try:
            rank = int(item_list[item_key])
            ItemsInSongbook.objects.filter(songbook=songbook,
                                           id=item_id
                                           ).update(rank=rank)
        except ValueError:
            if str(item_list[item_key]).lower() == 'x':
                ItemsInSongbook.objects.filter(
                        songbook=songbook,
                        id=item_id
                        ).delete()

    songbook.fill_holes()

    if request.POST['new_section']:
        try:
            section_name = unicode(request.POST['new_section'])
            songbook.add_section(section_name)
            messages.success(request, _(u"Nouvelle section ajoutée en fin de carnet"))
        except ValueError:
            messages.error(request, _(u"Ce nom de section n'est pas valide"))

    section_list = {}
    for key in request.POST.keys():
        if key.startswith('section_'):
            section_list[key] = request.POST[key]

    for key, section_name in section_list.items():
        item_id = int(key[8:])
        section = ItemsInSongbook.objects.get(songbook=songbook,
                                              id=item_id)

        if section.item.name != section_name:
            error, message = _clean_latex(section_name)
            if error:
                messages.error(request, message)
            else:
                section.item.name = section_name
                section.item.save()

    return redirect(next_url)

def _clean_latex(string):
        '''
        Return true if one of the LaTeX special characters
        is in the string
        '''
        TEX_CHAR = ['\\', '{', '}', '&', '[', ']', '^', '~']
        CHARS = ', '.join(['"{char}"'.format(char=char) for char in TEX_CHAR])
        MESSAGE = _(u"Les caractères suivant sont interdits, merci de les " +
                    u"supprimer : {chars}.".format(chars=CHARS))
        for char in TEX_CHAR:
            if char in string:
                return True, MESSAGE
        return False, ""


class DeleteSongbook(OwnerRequiredMixin, DeleteView):
    model = Songbook
    context_object_name = "songbook"
    template_name = 'generator/delete_songbook.html'

    def get_success_url(self):
        success_url = reverse_lazy('songbook_private_list')
        messages.success(self.request, _(u"Le carnet a été supprimé"), extra_tags='removal')
        return success_url

    def get_object(self, queryset=None):
        id = self.kwargs.get('id', None)
        slug = self.kwargs.get('slug', None)
        return get_object_or_404(Songbook, id=id, slug=slug)


class LayoutList(OwnerRequiredMixin, CreateView):
    """Setup the parameters for songbook rendering
    """
    model = Layout
    template_name = 'generator/setup_rendering.html'
    form_class = LayoutForm

    def get_success_url(self):
        return reverse('render_songbook',
                        kwargs={"id": self.kwargs["id"],
                                "slug": self.kwargs["slug"]})

    def form_valid(self, form):
        messages.success(self.request, _(u"La mise en page a été crée."))
        rst = super(LayoutList, self).form_valid(form)

        # Set the session for layout generation
        self.request.session["layout"] = self.object.id
        return rst

    def get_context_data(self, **kwargs):
        context = super(LayoutList, self).get_context_data(**kwargs)
        id = self.kwargs.get('id', None)
        slug = self.kwargs.get('slug', None)
        songbook = Songbook.objects.get(id=id, slug=slug)
        context['songbook'] = songbook
        context['form_options'] = LayoutForm.OPTIONS
        context['existing_tasks'] = GeneratorTask.objects.filter(
                                                    songbook=songbook)
        return context


@owner_required(('id', 'id'))
def render_songbook(request, id, slug):
    """Trigger the generation of a songbook
    """
    force = request.REQUEST.get("force", False)
    songbook = Songbook.objects.get(id=id)

    layout_id = request.REQUEST.get("layout", 0)

    if layout_id == 0:
        layout_id = request.session["layout"]

    layout = Layout.objects.get(id=layout_id)

    try:
        gen_task = GeneratorTask.objects.get(songbook=songbook,
                                             layout=layout)
        state = gen_task.state
    except GeneratorTask.DoesNotExist:
        gen_task = None
        state = None

    # Build cases
    build = gen_task is None or \
            ((state == GeneratorTask.State.FINISHED or \
              state == GeneratorTask.State.ERROR)  and force) or\
            gen_task.hash != songbook.hash()

    if build:
        gen_task, _created = GeneratorTask.objects.get_or_create(
                                    songbook=songbook,
                                    layout=layout)
        gen_task.result = {}
        gen_task.hash = songbook.hash()
        gen_task.state = GeneratorTask.State.QUEUED
        gen_task.save()

        import generator.tasks as tasks
        tasks.queue_render_task(gen_task.id)

    return redirect(reverse('setup_rendering', kwargs={"id":id, "slug":slug}))
