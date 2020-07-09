from lxml.objectify import ObjectifiedElement  # nosec
from pyvcloud.vcd.client import EntityType

from pyvcloud.vcd.client import Client, NSMAP, RelationType
from pyvcloud.vcd.vm import VM


class VmExtended(VM):
    def __init__(
        self,
        client: Client,
        href: ObjectifiedElement = None,
        resource: ObjectifiedElement = None,
    ) -> None:
        super().__init__(client, href, resource)

    def update_product_section_property(
        self,
        vm_product_sections_xml: ObjectifiedElement,
        key: str,
        class_name: str = "",
        instance_name: str = "",
        value: str = "",
        is_password: bool = False,
        user_configurable: bool = False,
    ) -> None:
        product_sections = vm_product_sections_xml.xpath(
            "ovf:ProductSection", namespaces=NSMAP
        )

        for product_section in product_sections:
            class_val = product_section.get("{" + NSMAP["ovf"] + "}class")
            instance_val = product_section.get("{" + NSMAP["ovf"] + "}instance")
            if class_name == class_val and instance_name == instance_val:
                properties = product_section.xpath("ovf:Property", namespaces=NSMAP)
                for property_node in properties:
                    property_key = property_node.get("{" + NSMAP["ovf"] + "}key")
                    if property_key == key:
                        property_node.set("{" + NSMAP["ovf"] + "}value", value)
                        property_node.set(
                            "{" + NSMAP["ovf"] + "}password", str(is_password).lower()
                        )
                        property_node.set(
                            "{" + NSMAP["ovf"] + "}userConfigurable",
                            str(user_configurable).lower(),
                        )
                        break
                break

    def send_updated_product_section(
        self, vm_product_sections_xml: ObjectifiedElement
    ) -> ObjectifiedElement:
        return self.client.put_linked_resource(
            vm_product_sections_xml,
            rel=RelationType.EDIT,
            media_type=EntityType.PRODUCT_SECTIONS.value,
            contents=vm_product_sections_xml,
        )
