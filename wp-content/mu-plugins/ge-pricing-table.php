<?php
/**
 * Plugin Name: GE – Stripe Pricing Table Shortcode
 * Description: Renders Stripe Pricing Table and sets client-reference-id to your app user_id.
 */

if (!defined('ABSPATH')) exit;

add_shortcode('ge_pricing_table', function($atts) {
  $a = shortcode_atts([
    'pricing_table_id' => '',
    'publishable_key'  => '',
  ], $atts, 'ge_pricing_table');

  if (empty($a['pricing_table_id']) || empty($a['publishable_key'])) {
    return '<p style="color:#c00">[ge_pricing_table] missing pricing_table_id or publishable_key.</p>';
  }

  // Pull your app user_id stored on the WP user (adjust meta key if different)
  $wp_uid = get_current_user_id();
  $ge_uid = $wp_uid ? get_user_meta($wp_uid, 'gaia_supabase_user_id', true) : '';

  ob_start(); ?>
  <div class="ge-pricing-wrap" data-ptid="<?php echo esc_attr($a['pricing_table_id']); ?>">
    <script async src="https://js.stripe.com/v3/pricing-table.js"></script>

    <stripe-pricing-table
      pricing-table-id="<?php echo esc_attr($a['pricing_table_id']); ?>"
      publishable-key="<?php echo esc_attr($a['publishable_key']); ?>">
    </stripe-pricing-table>

    <script>
    (function() {
      // 1) Determine user_id for client-reference-id
      var uid = <?php echo json_encode((string)$ge_uid); ?>;
      if (!uid) {
        // Fallbacks: ?uid=... or localStorage (optional)
        var qs = new URLSearchParams(location.search);
        uid = qs.get('uid') || (window.localStorage ? localStorage.getItem('ge_user_id') : '') || '';
      }

      // 2) Wait for the custom element then set attribute
      function setClientRef() {
        var el = document.querySelector('stripe-pricing-table[pricing-table-id="<?php echo esc_js($a['pricing_table_id']); ?>"]');
        if (el) {
          if (uid) el.setAttribute('client-reference-id', uid);
          return true;
        }
        return false;
      }

      if (!setClientRef()) {
        var obs = new MutationObserver(function() {
          if (setClientRef()) obs.disconnect();
        });
        obs.observe(document.documentElement, { childList: true, subtree: true });
      }
    })();
    </script>

    <style>
      .ge-pricing-wrap { display:block; max-width: 980px; margin: 0 auto; padding: 1rem; }
    </style>
  </div>
  <?php
  return ob_get_clean();
});