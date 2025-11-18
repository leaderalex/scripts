<?php
$landing_name = 'BKR_45LUCKY_YELLOW';
$campaign = 'baykar';  //ТУТ смотри какие есть под этот офер компейны в СРМ 
$source = 'Google';

$userDataApiKey = 'kdI8G5EX9F5nhTw1nWbC';
$userDataUserdID = '0f496d44-5031-49e7-b108-cb04c478024a'; //MORIS
$userDataUserName = 'Yellow';


$botToken = "7701810345:AAFxbwf25JyTX2e-8zP6Gy_pyQtQllY96ec";
$chatId = "-1002284183910";
$url = "https://api.telegram.org/bot$botToken/sendMessage";
// end Telegramm

$blocked_ips = [
    '176.220.225.221',
    '88.241.131.186',
    '46.155.254.192'
];

$post = $_POST; // get all POST data
$rawData = file_get_contents('php://input');
$data = json_decode($rawData, true);

$subid = $_COOKIE['_subid'] ?? $_COOKIE['subid'] ?? '';
$aff = $_COOKIE['aff'] ?? $_GET['aff'] ?? null;
$flow = $_COOKIE['flow'] ?? $_GET['flow'];
$pot = $flow;

function appendToJsonFile($file, $subid = null, $name = '', $phone = '', $lastName = '')
{

    if (empty($subid)) {
        return;
    }
    $data = file_exists($file) ? json_decode(file_get_contents($file), true) : [];


    if (!isset($data[$subid])) {
        $data[$subid] = [
            "name" => $name,
            "phone" => $phone,
            "lastName" => $lastName
        ];

        file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    }
}


if ($data == '') {
    die();
}


function logFile($request, $filename)
{
    $fOpen = fopen($filename, 'a');
    fwrite($fOpen, urldecode(http_build_query($request)) . "\r\n");
    fclose($fOpen);
}

function getIp()
{
    $keys = [
        'HTTP_CLIENT_IP',
        'HTTP_X_FORWARDED_FOR',
        'REMOTE_ADDR'
    ];
    foreach ($keys as $key) {
        if (!empty($_SERVER[$key])) {
            $ip = trim(end(explode(',', $_SERVER[$key])));
            if (filter_var($ip, FILTER_VALIDATE_IP)) {
                return $ip;
            }
        }
    }
}


$user = $_GET['utm_source'];
$postUrl = "https://api.space-crm.com/leads/new?apiKey=$userDataApiKey";
$name = $data['first_name'];
$lastName = $data['last_name'];
$email = $data['email'];
$phone = $data['phone'];
$ip = getIp();
$buer = $user;
$flow = $pot;
$code = $data['country_code'];
$pixelFB = $_GET['gclid'] ?? '';
$campaign_name = $_SERVER['HTTP_HOST'];

$fullName = explode(' ', trim($data['first_name']));

if (count($fullName) >= 2) {
    $name = $fullName[0];
    $lastName = $fullName[1];
} else {
    $name = $data['first_name'];
    $lastName = $data['last_name'];
}
if($source == 'Google') {
  $operatorCodes = [
  '+53',
  '+54',
];

foreach ($operatorCodes as $old) {
    if (strpos($phone, $old) === 0) {
        $phone = '+90' . substr($phone, strlen($old));
        break;
    }
}

}

if (in_array($ip, $blocked_ips)) {
    exit("error");
}

$dataPost = [
    "name" => $name,
    "surname" => $lastName,
    "country" => $code,
    "email" => $email,
    "landing" => $landing_name,
    "phoneNumber" => $phone,
    "userId" => $userDataUserdID,
    "ip" => $ip,
    "clickId" => $_COOKIE['subid'] ?? '3245tyrtjh',
    "campaign" => $campaign,
    'language' => 'TR',
    'source' => $source,
    'customParam1' => $_SERVER['QUERY_STRING'],
    'customParam3' => $pixelFB,
    'customParam4' => $_SERVER['HTTP_HOST'] . '&aff=' . $aff,
    'customParam6' => $_SERVER['HTTP_HOST'],
    'customParam7' => isset($_GET['utm_content']) ? (string) $_GET['utm_content'] : '',
    'customParam8' => isset($_GET['utm_campaign']) ? (string) $_GET['utm_campaign'] : '',
];


// logFile($dataPost, '../userdata/log/beforePOST-DATA-spase.log');


$curl = curl_init();
curl_setopt_array($curl, array(
    CURLOPT_URL => $postUrl,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_ENCODING => '',
    CURLOPT_MAXREDIRS => 10,
    CURLOPT_TIMEOUT => 0,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
    CURLOPT_CUSTOMREQUEST => 'POST',
    CURLOPT_POSTFIELDS => json_encode($dataPost),
    CURLOPT_HTTPHEADER => array(
        'Content-Type: application/json'
    ),
));


$response = curl_exec($curl);
curl_close($curl);

// $text = date(format: "d H:i:s") . ' | ' . json_encode($dataPost, JSON_UNESCAPED_UNICODE) . $response . "\n";
// $filename = "./lll/log/afterT-spase.log";
// $fh = fopen($filename, "a");
// fwrite($fh, $text);
// fclose($fh);


$new_data2 = json_decode($response, true);
if ($new_data2['success']) {
    $new_data2['status'] = 'ok';
    exit(json_encode($new_data2));
} else {
    $message =
        "New CRM \nDate: <b>" . date("d H:i:s") . "</b>\nName: <b>" .
        $name . "</b>\nLastName: <b>" . $lastName . "</b>\nEmail: <b>" . $email . "</b>\nPhone: <b>" . $phone .
        "</b>\nIp: <b>" . $ip . "</b>\nGeo: <b>" . $code . "</b>\nFlow: <b>" . $flow . "</b>\nBuers: <b>" . $buer .
        "</b>\nPixelFB: <b>" . $pixelFB . "</b>\nUtm_campaign: <b>" . $utm_campaign . "</b>\nAff: <b>" . $aff .
        "</b>\nError: <b>" . $response . "</b>";
    // $text =
    //     date("d H:i:s") . ' | ' . $name . ' | ' . $lastName . ' | ' . $phone . ' | ' . $email . ' | IP' . $ip . ' | utm_source' .
    //     $buer . ' | flow' . $flow . ' | ' . $code . "\n";
    // $filename = "./lll/beforeLogFile.log";
    // $fh = fopen($filename, "a");
    // fwrite($fh, $text);
    // fclose($fh);




    $params = array(
        'chat_id' => $chatId,
        'text' => $message,
        'parse_mode' => 'HTML',
    );
    $options = array(
        'http' => array(
            'header' => "Content-type: application/x-www-form-urlencoded\r\n",
            'method' => 'POST',
            'content' => http_build_query($params)
        )
    );
    $context = stream_context_create($options);
    $result = file_get_contents($url, false, $context);



    exit(json_encode($new_data2));
}
