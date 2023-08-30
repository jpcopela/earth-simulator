import yaml
import satpy.modifiers.atmosphere
import satpy.composites.abi
import satpy.composites.abi
import satpy.modifiers.filters
import satpy.composites.cloud_products
import satpy.composites.spectral

#ingest a satpy composites.yaml file and return a list of required channels for each composite
class CompositeHelper():
    def __init__(self, yaml_file):
        #load yaml file
        with open(yaml_file) as file:
            self.composites = yaml.load(file, Loader=yaml.FullLoader)
        
        visir_path = 'satpy_configs/composites/visir.yaml'
        with open(visir_path) as file:
            self.visir_composites = yaml.load(file, Loader=yaml.FullLoader)

    def get_composite_channels(self, composite_name):
        prerequisites = self._get_composite_prerequisites(composite_name)

        if prerequisites is not None:
            #if the name of the prerequisite is a secondary product (e.g. 'green'), then it should also be a composite
            #either in the file we are looking at or in the visir composites file. Otherwise, it is a primary product.
            channels = []
            for name in prerequisites:
                #if the name is a composite, then get the channels for that composite
                if (name in self.composites['composites'] or name in self.visir_composites['composites']):
                    channels.extend(self.get_composite_channels(name))
                else:
                    channels.append(name)

            return list(dict.fromkeys(channels))
        
        return
    
    def get_available_composites(self):
        return [i for i in self.composites['composites'].keys()]

    def _get_composite_prerequisites(self, composite_name):
        names = []
        composite = None        

        #try to find the prerequisites in the composites file, then the visir composites file
        try:
            composite = self.composites['composites'][composite_name]

        except KeyError:            
            try:
                composite = self.visir_composites['composites'][composite_name]['prerequisites']

            except KeyError:
                print(f'{composite_name} not found.')

        if composite is not None:
            if isinstance(composite, dict):
                for item1 in composite['prerequisites']:
                    if isinstance(item1, dict):
                        #depending on the composite the list can look different
                        #look for 'prerequisites' keys in the list items
                        if 'prerequisites' in item1.keys():
                            #sometimes the prerequisites are a list of dicts, sometimes a list of strings
                            for item2 in item1['prerequisites']:
                                if isinstance(item2, dict):
                                    if 'name' in item2.keys():
                                        names.append(item2['name'])
                                    else:
                                        print(f'{composite_name} has a prerequisite without a channel name. Unable to proceed.')
                                        return None
                                
                                elif isinstance(item2, str):
                                    names.append(item2)
                        else:
                            if 'name' in item1.keys():
                                names.append(item1['name'])
                            else:
                                print(f'{composite_name} has a prerequisite without a channel name. Unable to proceed.')
                                return None
                            
                    elif isinstance(item1, str):
                        names.append(item1)
            else:
                print(f'{composite_name} has an invalid layout. Unable to proceed.')
                return None
                    
        return names