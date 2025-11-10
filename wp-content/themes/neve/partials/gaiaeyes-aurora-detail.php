<?php
if (!defined('ABSPATH')) {
    exit;
}

$template = WP_CONTENT_DIR . '/mu-plugins/templates/gaiaeyes-aurora-detail.php';

if (file_exists($template)) {
    $template_args = isset($args) && is_array($args) ? $args : [];
    include $template;
    return;
}
?>
<div class="gaia-aurora__error">Aurora detail template missing.</div>
