import frappe

def before_install():
    # Check if 'contafacil' is in the installed apps
    installed_apps = frappe.get_installed_apps()
    if "contafacil" in installed_apps:
        print("Migrating data from contafacil to mfi_tools...")
        
        # 1. Update module references in metadata tables
        frappe.db.sql("UPDATE `tabDocType` SET module = 'MFI Tools' WHERE module = 'Contafacil'")
        frappe.db.sql("UPDATE `tabPage` SET module = 'MFI Tools' WHERE module = 'Contafacil'")
        frappe.db.sql("UPDATE `tabReport` SET module = 'MFI Tools' WHERE module = 'Contafacil'")
        frappe.db.sql("UPDATE `tabPrint Format` SET module = 'MFI Tools' WHERE module = 'Contafacil'")
        frappe.db.sql("UPDATE `tabWorkspace` SET module = 'MFI Tools' WHERE module = 'Contafacil'")
        
        # 2. Update Module Def
        if frappe.db.exists("Module Def", "Contafacil"):
            frappe.db.sql("UPDATE `tabModule Def` SET name = 'MFI Tools', app_name = 'mfi_tools' WHERE name = 'Contafacil'")
        else:
            # Just in case the module was already renamed, make sure app_name is updated
            frappe.db.sql("UPDATE `tabModule Def` SET app_name = 'mfi_tools' WHERE name = 'MFI Tools'")

        # 3. Update Patch Log
        frappe.db.sql("UPDATE `tabPatch Log` SET patch = REPLACE(patch, 'contafacil.contafacil', 'mfi_tools.mfi_tools') WHERE patch LIKE 'contafacil.contafacil%'")
            
        # 4. Remove old app from the list of installed apps
        from frappe.installer import remove_from_installed_apps
        remove_from_installed_apps("contafacil")
        
        # Commit changes to the database
        frappe.db.commit()
        print("Migration complete!")
