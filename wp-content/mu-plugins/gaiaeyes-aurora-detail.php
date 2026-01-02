<?php
$show_kp_lines = !empty($config['enable_kp_lines_toggle']);
?>
<?php if (!$show_kp_lines): ?>
  <style>
    /* Force-hide any KP-lines UI/overlay when feature is disabled */
    .ga-aurora [data-role="kp-lines-toggle"],
    .ga-aurora .ga-kp-lines,
    .ga-aurora .ga-aurora__legend--kplines,
    .ga-aurora .ga-aurora__panel--kplines { display: none !important; }
  </style>
<?php endif; ?>

<section class="ga-aurora" id="<?php echo esc_attr($section_id); ?>" data-kp-lines="<?php echo $show_kp_lines ? '1' : '0'; ?>">
