<?php if (!defined('ABSPATH')) exit;

if (!function_exists('gaiaeyes_http_get_json_api_cached')){
  function gaiaeyes_http_get_json_api_cached($url, $cache_key, $ttl, $bearer = '', $dev_user = ''){
    $cached = get_transient($cache_key);
    if ($cached !== false) return $cached;
    $headers = ['Accept'=>'application/json','User-Agent'=>'GaiaEyesWP/1.0'];
    if ($bearer)   $headers['Authorization'] = 'Bearer ' . $bearer;
    if ($dev_user) $headers['X-Dev-UserId']  = $dev_user;
    $resp = wp_remote_get(add_query_arg(['v'=>floor(time()/600)], $url), ['timeout'=>10,'headers'=>$headers]);
    $code = is_wp_error($resp) ? 0 : intval(wp_remote_retrieve_response_code($resp));
    if ($code < 200 || $code >= 300) return null;
    $data = json_decode(wp_remote_retrieve_body($resp), true);
    if (!is_array($data)) return null;
    set_transient($cache_key, $data, $ttl);
    return $data;
  }
}
