#include <glib.h>

#ifndef BD_MPATH
#define BD_MPATH

GQuark bd_mpath_error_quark (void);
#define BD_MPATH_ERROR bd_mpath_error_quark ()
typedef enum {
    BD_MPATH_ERROR_FLUSH,
} BDMpathError;

gboolean bd_mpath_flush_mpaths (GError **error);
gboolean bd_mpath_is_mpath_member (gchar *device, GError **error);
gboolean bd_mpath_set_friendly_names (gboolean enabled, GError **error);

#endif  /* BD_MPATH */
