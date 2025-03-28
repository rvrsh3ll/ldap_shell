from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from .base import BaseArgumentCompleter
from abc import abstractmethod
from ldap3 import SUBTREE
from ldap_shell.completers.base import ADObjectCacheManager

class ADObjectCompleter(BaseArgumentCompleter):
    """Completer for AD objects (users, computers, groups, OUs)"""
    highlight_color = None  # Base color, overridden in child classes
    attributes = ['sAMAccountName', 'name']  # Base set of attributes
    
    def __init__(self, ldap_connection, domain_dumper):
        self.ldap = ldap_connection
        self.domain_dumper = domain_dumper
        self.cache_manager = ADObjectCacheManager()

    def get_completions(self, document: Document, complete_event, current_word=None):
        if not isinstance(document, Document):
            return
        
        text = document.text_before_cursor
        in_quotes = (text.count('"') % 2) == 1 or (text.count("'") % 2) == 1
        
        # Get cache from manager
        cached_objects = self.cache_manager.get_cache(self.__class__.__name__)
        if cached_objects is None:
            cached_objects = self._get_ad_objects()
            self.cache_manager.set_cache(self.__class__.__name__, cached_objects)
        
        if text.endswith(' '):
            word_before_cursor = ''
        else:
            word_before_cursor = text.split()[-1] if text.split() else ''

        for obj in cached_objects:
            if ' ' in obj and not in_quotes:
                obj = f'"{obj}"'
            if word_before_cursor.lower() in obj.lower():
                display = self._highlight_match(obj, word_before_cursor)
                if self.highlight_color:
                    display = f"<style bg='{self.highlight_color}'>{display}</style>"
                yield Completion(
                    obj,
                    start_position=-len(word_before_cursor),
                    display=HTML(display)
                )

    def _highlight_match(self, text: str, substr: str) -> str:
        """Highlights the matching part of the text"""
        if not substr:
            return text
            
        index = text.lower().find(substr.lower())
        if index >= 0:
            before = text[:index]
            match = text[index:index + len(substr)]
            after = text[index + len(substr):]
            return f"{before}<b><style fg='black'>{match}</style></b>{after}"
        return text

    def _get_ad_objects(self):
        objects = set()
        ldap_filter = self.get_ldap_filter()
        
        try:
            # Use built-in method for pagination
            search_generator = self.ldap.extend.standard.paged_search(
                search_base=self.domain_dumper.root,
                search_filter=ldap_filter,
                search_scope=SUBTREE,
                attributes=self.attributes,
                paged_size=500,
                generator=True
            )
            
            for entry in search_generator:
                if entry['type'] != 'searchResEntry':
                    continue
                    
                # Priority attributes for each object type
                if self.primary_attribute in entry['attributes']:
                    objects.add(str(entry['attributes'][self.primary_attribute]))
                elif self.fallback_attribute in entry['attributes']:
                    objects.add(str(entry['attributes'][self.fallback_attribute]))
            
        except Exception as e:
            print(f"Error fetching AD objects: {str(e)}")
            
        return objects

    @abstractmethod
    def get_ldap_filter(self):
        """Each inheritor must define its own LDAP filter"""
        pass

class UserCompleter(ADObjectCompleter):
    highlight_color = "ansibrightgreen"  # Bright green background for users
    primary_attribute = 'sAMAccountName'
    fallback_attribute = 'name'
    
    def get_ldap_filter(self):
        return "(&(objectCategory=person)(objectClass=user))"

class ComputerCompleter(ADObjectCompleter):
    highlight_color = "ansibrightred"  # Bright red background for computers
    primary_attribute = 'sAMAccountName'
    fallback_attribute = 'name'
    
    def get_ldap_filter(self):
        return "(objectClass=computer)"

class GroupCompleter(ADObjectCompleter):
    highlight_color = "ansibrightyellow"  # Bright yellow background for groups
    primary_attribute = 'sAMAccountName'
    fallback_attribute = 'name'
    
    def get_ldap_filter(self):
        return "(objectClass=group)"

class OUCompleter(ADObjectCompleter):
    highlight_color = "ansibrightmagenta"  # Bright magenta background for OUs
    primary_attribute = 'name'
    fallback_attribute = 'distinguishedName'
    attributes = ['name', 'distinguishedName']  # Override attributes for OUs
    
    def get_ldap_filter(self):
        return "(objectClass=organizationalUnit)"