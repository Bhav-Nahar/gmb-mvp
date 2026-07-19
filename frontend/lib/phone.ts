export const COUNTRY_CODES = [
  { code: '+91', label: 'IN (+91)' },
  { code: '+1', label: 'US/CA (+1)' },
  { code: '+44', label: 'UK (+44)' },
  { code: '+61', label: 'AU (+61)' },
  { code: '+971', label: 'AE (+971)' },
  { code: '+65', label: 'SG (+65)' },
  { code: '+27', label: 'ZA (+27)' },
  { code: '+353', label: 'IE (+353)' },
  { code: '+64', label: 'NZ (+64)' },
  { code: '+49', label: 'DE (+49)' },
  { code: '+33', label: 'FR (+33)' },
  { code: '+39', label: 'IT (+39)' },
  { code: '+34', label: 'ES (+34)' },
  { code: '+55', label: 'BR (+55)' },
  { code: '+52', label: 'MX (+52)' },
  { code: '+81', label: 'JP (+81)' },
  { code: '+86', label: 'CN (+86)' },
  { code: '+82', label: 'KR (+82)' },
  { code: '+31', label: 'NL (+31)' },
  { code: '+41', label: 'CH (+41)' },
  { code: '+46', label: 'SE (+46)' },
  { code: '+47', label: 'NO (+47)' },
  { code: '+45', label: 'DK (+45)' },
  { code: '+358', label: 'FI (+358)' },
  { code: '+972', label: 'IL (+972)' },
  { code: '+966', label: 'SA (+966)' },
  { code: '+60', label: 'MY (+60)' },
  { code: '+62', label: 'ID (+62)' },
  { code: '+66', label: 'TH (+66)' },
  { code: '+84', label: 'VN (+84)' },
  { code: '+63', label: 'PH (+63)' },
  { code: '+20', label: 'EG (+20)' },
  { code: '+234', label: 'NG (+234)' },
  { code: '+254', label: 'KE (+254)' },
];

export function getInitialCountryCode(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz.includes('America/Sao_Paulo') || tz.includes('America/Bahia') || tz.includes('America/Fortaleza') || tz.includes('America/Manaus') || tz.includes('America/Belem') || tz.includes('America/Recife') || tz.includes('America/Maceio') || tz.includes('America/Boa_Vista') || tz.includes('America/Rio_Branco') || tz.includes('America/Cuiaba') || tz.includes('America/Campo_Grande') || tz.includes('America/Porto_Velho')) return '+55'; // Brazil first
    if (tz.includes('America/Mexico_City') || tz.includes('America/Monterrey') || tz.includes('America/Mazatlan') || tz.includes('America/Chihuahua') || tz.includes('America/Hermosillo') || tz.includes('America/Tijuana') || tz.includes('America/Cancun') || tz.includes('America/Merida') || tz.includes('America/Matamoros') || tz.includes('America/Ojinaga')) return '+52'; // Mexico
    if (tz.includes('America/')) return '+1'; // US/Canada fallback
    
    if (tz.includes('Europe/London')) return '+44';
    if (tz.includes('Europe/Berlin')) return '+49';
    if (tz.includes('Europe/Paris')) return '+33';
    if (tz.includes('Europe/Rome')) return '+39';
    if (tz.includes('Europe/Madrid')) return '+34';
    if (tz.includes('Europe/Amsterdam')) return '+31';
    if (tz.includes('Europe/Zurich')) return '+41';
    if (tz.includes('Europe/Stockholm')) return '+46';
    if (tz.includes('Europe/Oslo')) return '+47';
    if (tz.includes('Europe/Copenhagen')) return '+45';
    if (tz.includes('Europe/Helsinki')) return '+358';
    if (tz.includes('Europe/Dublin')) return '+353';
    
    if (tz.includes('Australia/')) return '+61';
    if (tz.includes('Pacific/Auckland')) return '+64';
    
    if (tz.includes('Asia/Dubai')) return '+971';
    if (tz.includes('Asia/Singapore')) return '+65';
    if (tz.includes('Asia/Tokyo')) return '+81';
    if (tz.includes('Asia/Shanghai') || tz.includes('Asia/Chongqing') || tz.includes('Asia/Harbin') || tz.includes('Asia/Urumqi') || tz.includes('Asia/Kashgar')) return '+86';
    if (tz.includes('Asia/Seoul')) return '+82';
    if (tz.includes('Asia/Jerusalem')) return '+972';
    if (tz.includes('Asia/Riyadh')) return '+966';
    if (tz.includes('Asia/Kuala_Lumpur') || tz.includes('Asia/Kuching')) return '+60';
    if (tz.includes('Asia/Jakarta') || tz.includes('Asia/Pontianak') || tz.includes('Asia/Makassar') || tz.includes('Asia/Jayapura')) return '+62';
    if (tz.includes('Asia/Bangkok')) return '+66';
    if (tz.includes('Asia/Ho_Chi_Minh')) return '+84';
    if (tz.includes('Asia/Manila')) return '+63';
    if (tz.includes('Asia/Calcutta') || tz.includes('Asia/Kolkata')) return '+91';

    if (tz.includes('Africa/Johannesburg')) return '+27';
    if (tz.includes('Africa/Cairo')) return '+20';
    if (tz.includes('Africa/Lagos')) return '+234';
    if (tz.includes('Africa/Nairobi')) return '+254';
  } catch (e) {
    // Ignore error
  }
  return '+91'; // Fallback
}

export function parsePhoneState(rawPhone: string | null | undefined): { code: string, digits: string } {
  const defaultPhone = rawPhone || '';
  const matchedCode = COUNTRY_CODES.find(c => defaultPhone.startsWith(c.code))?.code || getInitialCountryCode();
  const digits = defaultPhone.startsWith(matchedCode) 
    ? defaultPhone.slice(matchedCode.length) 
    : defaultPhone.replace(/^\+/, '');
  return { code: matchedCode, digits };
}
