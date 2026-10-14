"""图协议、定义目录、资源适配与编译的公开入口。"""
from .Protocol import (
    Block, BindingValue, Collection, CollectionItem, DefinitionDescriptor, DefinitionRef,
    Diagnostic, FieldDescriptor, GraphDocument, LiteralValue, Reference, ResourceDescriptor,
    ResourceReference, TypeDescriptor,
)
from .Metadata import TypeRegistry, describe_fields
from .Definitions import (
    Definition, DefinitionRegistry, create_default_registry, register_application_definitions, register_extension_definitions,
)
from .Compiler import Compilation, GraphError, SourceMapping, compile_graph, describe_block, validate_graph
from .Resources import (
    RESOURCE_RESOLVER_KEY, DBPoolResourceResolver, MappingResourceResolver, RegistryResourceResolver,
    ResourceCatalog, ResourceResolver,
)
from .Sources import ResourceFactor, register_source_definitions
from .Nodes import SelectResult
from .Templates import TemplateRecipe, export_template, import_template, insert_template
