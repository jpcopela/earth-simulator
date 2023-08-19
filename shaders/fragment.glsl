#version 400

uniform sampler2D image;
uniform float time;
uniform int numLayers;

in vec2 texCoord;
in vec3 vertexCoord;

void main() {
   //float interp_value = time * numLayers;
   //float layer1 = floor(interp_value);
   //float layer2 = layer1 + 1.0;

   vec4 color;
   vec4 color1 = vec4(0.1, 0.3, 0.3, 1.0);
   vec4 color2 = vec4(0.1, 0.4, 0.2, 1.0);
   float r_dist = color2.r - color1.r;
   float g_dist = color2.g - color1.g;
   float b_dist = color2.b - color1.b;

   if (texture(image, texCoord).a < 0.2) {
      discard;
   }

   if (texCoord.x < 0.0 || texCoord.x > 1.0 || texCoord.y < 0.0 || texCoord.y > 1.0) {
      discard;
   }
   vec3 norm_vertex = normalize(vertexCoord);

   vec4 offset = vec4(r_dist * norm_vertex.z, g_dist * norm_vertex.y, b_dist * norm_vertex.x, 1.0);

   //this is the value of the default image
   if (texture(image, texCoord).ra == vec2(1.0, 1.0)) {
      color = vec4(offset.r + color1.r, offset.g + color1.g, offset.b + color1.b, 1.0);//#vec4(normalize(vertexCoord) / 1.5, 1.0);
   }
   else {
      color = vec4(texture(image, texCoord).rgb, 1.0);
   }

   gl_FragColor = color;
}